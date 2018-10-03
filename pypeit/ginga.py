""" Module for ginga routines.  Mainly for debugging
"""
from __future__ import (print_function, absolute_import, division, unicode_literals)

try:
    basestring
except NameError:
    basestring = str

import os
import numpy as np
import time

# CANNOT LOAD DEBUGGER AS THIS MODULE IS CALLED BY ARDEBUG
#from pypeit import ardebug as debugger
#import pdb as debugger
#from pypeit import scienceimage

from ginga.util import grc

from astropy.io import fits

from pypeit import msgs

def connect_to_ginga(host='localhost', port=9000, raise_err=False):
    """ Connect to an active RC Ginga
    Parameters
    ----------
    host : str, optional
    port : int, optional

    Returns
    -------
    viewer : RemoteClient
      connectoin to Ginga

    """
    # Start
    viewer = grc.RemoteClient(host, port)
    # Test
    ginga = viewer.shell()
    try:
        tmp = ginga.get_current_workspace()
    except:
        if raise_err:
            raise ValueError
        else:
            msgs.warn("Problem connecting to Ginga.  Launch an RC Ginga viewer: ginga --module=RC   then continue.")
            debugger.set_trace()
    # Return
    return viewer


def show_image(inp, chname='Image', waveimg=None, bitmask=None, mask=None, exten=0, cuts=None,
               clear=False, wcs_match=False):
    """
    Display an image using Ginga.

    .. todo::
        - implement instrument specific reading
        - use the `mask` as a boolean mask if `bitmask` is not provided.

    Args:
        inp (:obj:`str`, numpy.ndarray):
            The image to view.  If a string is provided, it must be the
            name of a fits image that can be read by `astropy.io.fits`.
        chname (:obj:`str`, optional):
            The name of the ginga channel to use.
        waveimg (:obj:`str`, optional):
            The name of a fits image with the relevant WCS coordinates
            in its header, mainly for wavelength array.  If None, no WCS
            is used.
        bitmask (:class:`pypeit.bitmask.BitMask`, optional):
            The object used to unpack the mask values.  If this is
            provided, mask must also be provided and the expectation is
            that a extraction image is being shown.
        mask (numpy.ndarray, optional):
            A boolean or bitmask array that designates a pixel as being
            masked.  Currently this is only used when displaying the
            spectral extraction result.
        exten (:obj:`int`, optional):
            The extension of the fits file with the image to show.  This
            is only used if the input is a file name.
        cuts (array-like, optional):
            Initial cut levels to apply when displaying the image.  This
            object must have a length of 2 with the lower and upper
            levels, respectively.
        clear (:obj:`bool`, optional):
            Clear any existing ginga viewer and its channels.
        wcs_match(:obj:`bool`, optional):
            Use this as a reference image for the WCS and match all
            image in other channels to it.

    Returns:
        ginga.util.grc.RemoteClient, ginga.util.grc._channel_proxy: The
        ginga remote client and the channel with the displayed image.

    Raises:
        ValueError:
            Raised if `cuts` is provided and does not have two elements
            or if bitmask is provided but mask is not.
    """
    # Input checks
    if cuts is not None and len(cuts) != 2:
        raise ValueError('Input cuts must only have two elements, the lower and upper cut.')
    if bitmask is not None and mask is None:
        raise ValueError('If providing a bitmask, must also provide the mask values.')

    # Read or set the image data.  This will fail if the input is a
    # string and astropy.io.fits cannot read the image.
    img = fits.open(inp)[exten].data if isinstance(inp, basestring) else inp

    # Instantiate viewer
    viewer = connect_to_ginga()
    if clear:
        # Clear existing channels
        shell = viewer.shell()
        chnames = shell.get_channel_names()
        for ch in chnames:
            shell.delete_channel(ch)
    ch = viewer.channel(chname)

    # Header
    header = {}
    header['NAXIS1'] = img.shape[1]
    header['NAXIS2'] = img.shape[0]
    if waveimg is not None:
        header['WCS-XIMG'] = waveimg

    # Giddy up
    ch.load_np(chname, img, 'fits', header)
    canvas = viewer.canvas(ch._chname)

    # These commands set up the viewer. They can be found at
    # ginga/ginga/ImageView.py
    out = canvas.clear()
    if cuts is not None:
        out = ch.cut_levels(cuts[0], cuts[1])
    out = ch.set_color_map('ramp')
    out = ch.set_intensity_map('ramp')
    out = ch.set_color_algorithm('linear')
    out = ch.restore_contrast()
    out = ch.restore_cmap()

    # WCS Match this to other images with this as the reference image?
    if wcs_match:
        # After displaying all the images since up the images with WCS_MATCH
        shell = viewer.shell()
        out = shell.start_global_plugin('WCSMatch')
        out = shell.call_global_plugin_method('WCSMatch', 'set_reference_channel', [chname], {})

    # TODO: I would prefer to change the color map to indicate these
    # pixels rather than overplot points. Because for large numbers of
    # masked pixels, this is super slow. Need to ask ginga folks how to
    # do that.

    # If bitmask was passed in, assume this is an extraction qa image
    # and use the mask to identify why each pixel was masked
    if bitmask is not None:
        # Unpack the bitmask
        bpm, crmask, satmask, minmask, offslitmask, nanmask, ivar0mask, ivarnanmask, extractmask \
                = bitmask.unpack(mask)

        # These are the pixels that were masked by the bpm
        spec_bpm, spat_bpm = np.where(bpm & ~offslitmask)
        nbpm = len(spec_bpm)
        # note: must cast numpy floats to regular python floats to pass the remote interface
        points_bpm = [dict(type='point', args=(float(spat_bpm[i]), float(spec_bpm[i]), 2),
                           kwargs=dict(style='plus', color='magenta')) for i in range(nbpm)]

        # These are the pixels that were masked by LACOSMICS
        spec_cr, spat_cr = np.where(crmask & ~offslitmask)
        ncr = len(spec_cr)
        # note: must cast numpy floats to regular python floats to pass the remote interface
        points_cr = [dict(type='point', args=(float(spat_cr[i]), float(spec_cr[i]), 2),
                             kwargs=dict(style='plus', color='cyan')) for i in range(ncr)]

        # These are the pixels that were masked by the extraction
        spec_ext, spat_ext = np.where(extractmask & ~offslitmask)
        next = len(spec_ext)
        # note: must cast numpy floats to regular python floats to pass the remote interface
        points_ext = [dict(type='point', args=(float(spat_ext[i]), float(spec_ext[i]), 2),
                            kwargs=dict(style='plus', color='red')) for i in range(next)]

        # These are the pixels that were masked for any other reason
        spec_oth, spat_oth = np.where(satmask | minmask | nanmask | ivar0mask | ivarnanmask
                                      & ~offslitmask)
        noth = len(spec_oth)
        # note: must cast numpy floats to regular python floats to pass
        # the remote interface
        points_oth = [dict(type='point', args=(float(spat_oth[i]), float(spec_oth[i]), 2),
                            kwargs=dict(style='plus', color='yellow')) for i in range(noth)]

        nspat = img.shape[1]
        nspec = img.shape[0]
        # Labels for the points
        text_bpm = [dict(type='text', args=(nspat / 2 -40, nspec / 2, 'BPM'),
                           kwargs=dict(color='magenta', fontsize=20))]

        text_cr = [dict(type='text', args=(nspat / 2 -40, nspec / 2 - 30, 'CR'),
                           kwargs=dict(color='cyan', fontsize=20))]

        text_ext = [dict(type='text', args=(nspat / 2 -40, nspec / 2 - 60, 'EXTRACT'),
                          kwargs=dict(color='red', fontsize=20))]

        text_oth = [dict(type='text', args=(nspat / 2 -40, nspec / 2 - 90, 'OTHER'),
                          kwargs=dict(color='yellow', fontsize=20))]

        canvas_list = points_bpm + points_cr + points_ext + points_oth + text_bpm + text_cr \
                        + text_ext + text_oth
        canvas.add('constructedcanvas', canvas_list)

    return viewer, ch


def show_slits(viewer, ch, lord_in, rord_in, slit_ids = None, rotate=False, pstep=1, clear = False):
    """ Overplot slits on image in Ginga
    Parameters
    ----------
    viewer
    ch
    lord_in : ndarray
    rord_in : ndarray
    slit_ids : list of int
    rotate : bool, optional
      Allow for a rotated image
    pstep : int
      Show every pstep point of the edges
    clear: bool
      Clear the canvas?
    """

    # This allows the input lord and rord to either be (nspec, nslit) arrays or a single
    # vectors of size (nspec)
    if lord_in.ndim == 2:
        nslit = lord_in.shape[1]
        lordloc = lord_in
        rordloc = rord_in
    else:
        nslit = 1
        lordloc = lord_in.reshape(lord_in.size,1)
        rordloc = rord_in.reshape(rord_in.size,1)

    if slit_ids is None:
        slit_ids = [str(slit) for slit in np.arange(nslit)]

    # Deal with case that slit_ids is input as a scalar
    if hasattr(slit_ids,"__len__") == False:
        slit_ids = [slit_ids]

    # Canvas
    canvas = viewer.canvas(ch._chname)
    if clear:
        canvas.clear()
    # y-axis
    y = (np.arange(lordloc.shape[0])).tolist()
    #ohf = lordloc.shape[0] // 2
    tthrd = int(2*lordloc.shape[0]/3.)
    # Loop on slits
    for slit in range(lordloc.shape[1]):
        # Edges
        for kk,item in enumerate([lordloc, rordloc]):
            if kk == 0:
                clr = str('green')
            else:
                clr = str('red')
            if rotate:
                points = list(zip(y[::pstep],item[::pstep,slit].tolist()))
            else:
                points = list(zip(item[::pstep,slit].tolist(),y[::pstep]))
            canvas.add(str('path'), points, color=clr)
        # Text -- Should use the 'real' name
        if rotate:
            xt, yt = float(y[tthrd]), float(lordloc[tthrd,slit])
        else:
            xt, yt = float(lordloc[tthrd,slit]), float(y[tthrd])
        canvas.add(str('text'), xt, yt, str('S{:}'.format(slit_ids[slit])), color=str('red'),
                   fontsize=20.)

def show_trace(viewer, ch, trace, trc_name = 'Trace', color='blue', clear=False,
               rotate=False, pstep=1):
    """
    rotate : bool, optional
      Allow for a rotated image
    pstep : int
      Show every pstep point of the edges
    """
    # Canvas
    canvas = viewer.canvas(ch._chname)
    if clear:
        canvas.clear()
    # Show
    y = (np.arange(trace.size)[::pstep]).tolist()
    xy = [trace[::pstep].tolist(), y]
    if rotate:
        xy[0], xy[1] = xy[1], xy[0]
    points = list(zip(xy[0], xy[1]))
    canvas.add(str('path'), points, color=str(color))
    # Text
    ohf = trace.size // (2*pstep)
    xyt = [float(trace[ohf]), float(y[ohf])]
    if rotate:
        xyt[0], xyt[1] = xyt[1], xyt[0]
    canvas.add(str('text'), xyt[0], xyt[1], trc_name, rot_deg=90., color=str(color), fontsize=17.)


def clear_canvas(cname):
    viewer = connect_to_ginga()
    ch = viewer.channel(cname)
    canvas = viewer.canvas(ch._chname)
    canvas.clear()


def chk_arc_tilts(msarc, trcdict, sedges=None, yoff=0., xoff=0., all_green=False, pstep=10,
                  cname='ArcTilts'):
    """  Display arc image and overlay the arcline tilt measurements
    Parameters
    ----------
    msarc : ndarray
    trcdict : dict
      Contains trace info
    sedges : tuple
      Arrays of the slit
    xoff : float, optional
      In case Ginga has an index offset.  It appears not to
    yoff : float, optional


    Returns
    -------

    """
    # Connect
    viewer = connect_to_ginga()
    ch = viewer.channel(cname)
    canvas = viewer.canvas(ch._chname)
    # Show image, clear canvas [in case this is a repeat]
    name='image'
    ch.load_np(name, msarc, 'fits', {})
    canvas.clear()
    # Show a trace
    ntrc = len(trcdict['xtfit'])
    for idx in range(ntrc):
        if trcdict['xtfit'][idx] is None:
            continue
        x = trcdict['xtfit'][idx] + xoff
        y = trcdict['ytfit'][idx] + yoff  # FOR IMAGING (Ginga offsets this value by 1 internally)
        gdy = y > 0.
        if np.sum(gdy) > 0:
            points = list(zip(x[gdy][::pstep].tolist(),y[gdy][::pstep].tolist()))
            if trcdict['aduse'][idx]:
                clr = 'green'  # Good line
            else:
                if not all_green:
                    clr = 'red'  # Bad line
                else:
                    clr = 'green'
            canvas.add('path', points, color=clr)
    #msgs.info("Check the Ginga viewer")
    # Show slit edges
    if sedges is not None:
        y = (np.arange(msarc.shape[0]) + yoff).tolist()
        # Left
        for edge in [0,1]:
            points = list(zip(sedges[edge][::50].tolist(),y[::50]))
            canvas.add('path', points, color='cyan')
    # ALTERNATE for comparing methods
    if 'save_yt' in trcdict.keys():
        x = trcdict['xtfit'][2]
        y = trcdict['save_yt']
        gdy = y > 0.
        points = list(zip(x[gdy].tolist(),y[gdy].tolist()))
        canvas.add('path', points, color='blue')
    #debugger.set_trace()
