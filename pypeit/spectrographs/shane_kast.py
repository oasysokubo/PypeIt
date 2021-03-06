""" Module for Shane/Kast specific codes
"""
import numpy as np
import os
from pkg_resources import resource_filename

from astropy.time import Time

from pypeit import msgs
from pypeit import telescopes
from pypeit.core import framematch
from pypeit.par import pypeitpar
from pypeit.spectrographs import spectrograph

from pypeit import debugger


class ShaneKastSpectrograph(spectrograph.Spectrograph):
    """
    Child to handle Shane/Kast specific code
    """
    def __init__(self):
        # Get it started
        super(ShaneKastSpectrograph, self).__init__()
        self.spectrograph = 'shane_kast'
        self.telescope = telescopes.ShaneTelescopePar()
        #self.timeunit = 'isot'

    @staticmethod
    def default_pypeit_par():
        """
        Set default parameters for Shane Kast reductions.
        """
        par = pypeitpar.PypeItPar()
        # Frame numbers
        par['calibrations']['standardframe']['number'] = 1
        par['calibrations']['biasframe']['number'] = 5
        par['calibrations']['pixelflatframe']['number'] = 5
        par['calibrations']['traceframe']['number'] = 5
        par['calibrations']['arcframe']['number'] = 1


        # Scienceimage default parameters
        par['scienceimage'] = pypeitpar.ScienceImagePar()
        # Always flux calibrate, starting with default parameters
        par['fluxcalib'] = pypeitpar.FluxCalibrationPar()
        # Always correct for flexure, starting with default parameters
        par['flexure']['method'] = 'boxcar'
        # Set the default exposure time ranges for the frame typing
        par['calibrations']['biasframe']['exprng'] = [None, 1]
        par['calibrations']['darkframe']['exprng'] = [999999, None]     # No dark frames
        par['calibrations']['pinholeframe']['exprng'] = [999999, None]  # No pinhole frames
        par['calibrations']['pixelflatframe']['exprng'] = [0, None]
        par['calibrations']['traceframe']['exprng'] = [0, None]
        par['calibrations']['arcframe']['exprng'] = [None, 61]
        par['calibrations']['standardframe']['exprng'] = [1, 61]
        par['scienceframe']['exprng'] = [61, None]
        return par

    def compound_meta(self, headarr, meta_key):
        if meta_key == 'mjd':
            time = headarr[0]['DATE']
            ttime = Time(time, format='isot')
            return ttime.mjd
        else:
            msgs.error("Not ready for this compound meta")

    def init_meta(self):
        """
        Generate the meta data dict
        Note that the children can add to this

        Returns:
            self.meta: dict (generated in place)

        """
        meta = {}
        # Required (core)
        meta['ra'] = dict(ext=0, card='RA')
        meta['dec'] = dict(ext=0, card='DEC')
        meta['target'] = dict(ext=0, card='OBJECT')
        # dispname is arm specific (blue/red)
        meta['decker'] = dict(ext=0, card='SLIT_N')
        meta['binning'] = dict(ext=0, card=None, default='1,1')
        meta['mjd'] = dict(ext=0, card=None, compound=True)
        meta['exptime'] = dict(ext=0, card='EXPTIME')
        meta['airmass'] = dict(ext=0, card='AIRMASS')
        # Additional ones, generally for configuration determination or time
        meta['dichroic'] = dict(ext=0, card='BSPLIT_N')
        lamp_names = [ '1', '2', '3', '4', '5',
                       'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K']
        for kk,lamp_name in enumerate(lamp_names):
            meta['lampstat{:02d}'.format(kk+1)] = dict(ext=0, card='LAMPSTA{0}'.format(lamp_name))
        # Ingest
        self.meta = meta

    def configuration_keys(self):
        """
        Set the configuration keys

        Returns:
            cfg_keys: list

        """
        # decker is not included because arcs are often taken with a 0.5" slit
        return ['dispname', 'dichroic' ]

    def check_frame_type(self, ftype, fitstbl, exprng=None):
        """
        Check for frames of the provided type.
        """
        good_exp = framematch.check_frame_exptime(fitstbl['exptime'], exprng)
        if ftype in ['science', 'standard']:
            return good_exp & self.lamps(fitstbl, 'off')
#            \
#                        & np.array([ t not in ['Arcs', 'Bias', 'Dome Flat']
#                                        for t in fitstbl['target']])
        if ftype == 'bias':
            return good_exp # & (fitstbl['target'] == 'Bias')
        if ftype in ['pixelflat', 'trace']:
            # Flats and trace frames are typed together
            return good_exp & self.lamps(fitstbl, 'dome') # & (fitstbl['target'] == 'Dome Flat')
        if ftype in ['pinhole', 'dark']:
            # Don't type pinhole or dark frames
            return np.zeros(len(fitstbl), dtype=bool)
        if ftype in ['arc', 'tilt']:
            return good_exp & self.lamps(fitstbl, 'arcs')#  & (fitstbl['target'] == 'Arcs')

        msgs.warn('Cannot determine if frames are of type {0}.'.format(ftype))
        return np.zeros(len(fitstbl), dtype=bool)
  
    def lamps(self, fitstbl, status):
        """
        Check the lamp status.

        Args:
            fitstbl (:obj:`astropy.table.Table`):
                The table with the fits header meta data.
            status (:obj:`str`):
                The status to check.  Can be `off`, `arcs`, or `dome`.
        
        Returns:
            numpy.ndarray: A boolean array selecting fits files that
            meet the selected lamp status.

        Raises:
            ValueError:
                Raised if the status is not one of the valid options.
        """
        if status == 'off':
            # Check if all are off
            return np.all(np.array([ (fitstbl[k] == 'off') | (fitstbl[k] == 'None')
                                        for k in fitstbl.keys() if 'lampstat' in k]), axis=0)
        if status == 'arcs':
            # Check if any arc lamps are on
            arc_lamp_stat = [ 'lampstat{0:02d}'.format(i) for i in range(6,17) ]
            return np.any(np.array([ fitstbl[k] == 'on' for k in fitstbl.keys()
                                            if k in arc_lamp_stat]), axis=0)
        if status == 'dome':
            # Check if any dome lamps are on
            dome_lamp_stat = [ 'lampstat{0:02d}'.format(i) for i in range(1,6) ]
            return np.any(np.array([ fitstbl[k] == 'on' for k in fitstbl.keys()
                                            if k in dome_lamp_stat]), axis=0)
        raise ValueError('No implementation for status = {0}'.format(status))

class ShaneKastBlueSpectrograph(ShaneKastSpectrograph):
    """
    Child to handle Shane/Kast blue specific code
    """
    def __init__(self):
        # Get it started
        super(ShaneKastBlueSpectrograph, self).__init__()
        self.spectrograph = 'shane_kast_blue'
        self.camera = 'KASTb'
        self.detector = [
                # Detector 1
                pypeitpar.DetectorPar(
                            dataext         = 0,
                            specaxis        = 1,
                            specflip        = False,
                            xgap            = 0.,
                            ygap            = 0.,
                            ysize           = 1.,
                            platescale      = 0.43,
                            darkcurr        = 0.0,
                            saturation      = 65535.,
                            nonlinear       = 0.76,
                            numamplifiers   = 2,
                            gain            = [1.2, 1.2],
                            ronoise         = [3.7, 3.7],
                            datasec         = [ '[1:1024,:]', '[1025:2048,:]'],
                            oscansec        = [ '[2050:2080,:]', '[2081:2111,:]'],
                            suffix          = '_blue'
                            )]
        self.numhead = 1
        # Uses timeunit from parent class
        # Uses default primary_hdrext
        self.sky_file = 'sky_kastb_600.fits'

    def default_pypeit_par(self):
        """
        Set default parameters for Shane Kast Blue reductions.
        """
        par = ShaneKastSpectrograph.default_pypeit_par()
        par['rdx']['spectrograph'] = 'shane_kast_blue'
        par['flexure']['spectrum'] = os.path.join(resource_filename('pypeit', 'data/sky_spec/'),
                                                  'sky_kastb_600.fits')
        # 1D wavelength solution
        par['calibrations']['wavelengths']['sigdetect'] = 5.
        par['calibrations']['wavelengths']['rms_threshold'] = 0.20
        par['calibrations']['wavelengths']['lamps'] = ['CdI','HgI','HeI']

        par['calibrations']['wavelengths']['method'] = 'full_template'
        par['calibrations']['wavelengths']['n_first'] = 3
        par['calibrations']['wavelengths']['match_toler'] = 2.5
        par['calibrations']['wavelengths']['nonlinear_counts'] = self.detector[0]['nonlinear'] * self.detector[0]['saturation']

        # Set wave tilts order
        par['calibrations']['tilts']['spat_order'] = 3
        par['calibrations']['tilts']['spec_order'] = 5
        par['calibrations']['tilts']['maxdev_tracefit'] = 0.02
        par['calibrations']['tilts']['maxdev2d'] = 0.02

        return par

    def config_specific_par(self, scifile, inp_par=None):
        """
        Modify the PypeIt parameters to hard-wired values used for
        specific instrument configurations.

        .. todo::
            Document the changes made!

        Args:
            scifile (str):
                File to use when determining the configuration and how
                to adjust the input parameters.
            inp_par (:class:`pypeit.par.parset.ParSet`, optional):
                Parameter set used for the full run of PypeIt.  If None,
                use :func:`default_pypeit_par`.

        Returns:
            :class:`pypeit.par.parset.ParSet`: The PypeIt paramter set
            adjusted for configuration specific parameter values.
        """
        par = self.default_pypeit_par() if inp_par is None else inp_par
        # TODO: Should we allow the user to override these?

        if self.get_meta_value(scifile, 'dispname') == '600/4310':
            par['calibrations']['wavelengths']['reid_arxiv'] = 'shane_kast_blue_600.fits'
        elif self.get_meta_value(scifile, 'dispname') == '452/3306':
            par['calibrations']['wavelengths']['reid_arxiv'] = 'shane_kast_blue_452.fits'
        elif self.get_meta_value(scifile, 'dispname') == '830/3460':  # NOT YET TESTED
            par['calibrations']['wavelengths']['reid_arxiv'] = 'shane_kast_blue_830.fits'
        else:
            msgs.error("NEED TO ADD YOUR GRISM HERE!")
        # Return
        return par


    def init_meta(self):
        """
        Meta data specific to shane_kast_blue

        Returns:

        """
        super(ShaneKastBlueSpectrograph, self).init_meta()
        # Add the name of the dispersing element
        # dispangle and filter1 are not defined for Shane Kast Blue

        # Required
        self.meta['dispname'] = dict(ext=0, card='GRISM_N')
        # Additional (for config)


class ShaneKastRedSpectrograph(ShaneKastSpectrograph):
    """
    Child to handle Shane/Kast red specific code
    """
    def __init__(self):

        # Get it started
        super(ShaneKastRedSpectrograph, self).__init__()
        self.spectrograph = 'shane_kast_red'
        self.camera = 'KASTr'
        self.detector = [
                # Detector 1
                pypeitpar.DetectorPar(
                            dataext         = 0,
                            specaxis        = 0,
                            specflip        = False,
                            xgap            = 0.,
                            ygap            = 0.,
                            ysize           = 1.,
                            platescale      = 0.43,
                            darkcurr        = 0.0,
                            saturation      = 65535.,
                            nonlinear       = 0.76,
                            numamplifiers   = 2,
                            gain            = [1.9, 1.9],
                            ronoise         = [3.8, 3.8],
                            datasec         = ['[40:102,:]', '[103:347,:]'],
                            oscansec        = ['[425:522,:]', '[524:610,:]'],
                            suffix          = '_red'
                            )]
        self.numhead = 1
        # Uses timeunit from parent class
        # Uses default primary_hdrext
        # self.sky_file = ?

    def default_pypeit_par(self):
        """
        Set default parameters for Shane Kast Red reductions.
        """
        par = ShaneKastSpectrograph.default_pypeit_par()
        par['rdx']['spectrograph'] = 'shane_kast_red'

        # 1D wavelength solution
        par['calibrations']['wavelengths']['lamps'] = ['NeI','HgI','HeI','ArI']
        par['calibrations']['wavelengths']['nonlinear_counts'] = self.detector[0]['nonlinear'] * self.detector[0]['saturation']

        return par

    def init_meta(self):
        """
        Meta data specific to shane_kast_blue

        Returns:

        """
        super(ShaneKastRedSpectrograph, self).init_meta()
        # Add the name of the dispersing element
        # dispangle is not defined for Shane Kast Blue

        # Required
        self.meta['dispname'] = dict(ext=0, card='GRATNG_N')
        self.meta['dispangle'] = dict(ext=0, card='GRTILT_P')
        # Additional (for config)


    def check_header(self, headers):
        """
        Check headers match expectations for a Shane Kast red exposure.

        See also
        :func:`pypeit.spectrographs.spectrograph.Spectrograph.check_headers`.

        Args:
            headers (list):
                A list of headers read from a fits file
        """
        expected_values = {   '0.NAXIS': 2,
                            '0.DSENSOR': '2k x 4k Hamamatsu' }
        super(ShaneKastRedSpectrograph, self).check_headers(headers,
                                                            expected_values=expected_values)

    def header_keys(self):
        """
        Header keys specific to shane_kast_red

        Returns:

        """
        hdr_keys = super(ShaneKastRedSpectrograph, self).header_keys()
        hdr_keys[0]['dispname'] = 'GRATING_N'
        hdr_keys[0]['filter1'] = 'RDFILT_N'
        hdr_keys[0]['dispangle'] = 'GRTILT_P'
        return hdr_keys



class ShaneKastRedRetSpectrograph(ShaneKastSpectrograph):
    """
    Child to handle Shane/Kast red specific code
    """
    def __init__(self):
        # Get it started
        super(ShaneKastRedRetSpectrograph, self).__init__()
        self.spectrograph = 'shane_kast_red_ret'
        # WARNING: This is not unique wrt ShaneKastRed...
        self.camera = 'KASTr'
        self.detector = [
                # Detector 1
                pypeitpar.DetectorPar(
                            dataext         = 0,
                            specaxis        = 1,
                            specflip        = False,
                            xgap            = 0.,
                            ygap            = 0.,
                            ysize           = 1.,
                            platescale      = 0.774,
                            darkcurr        = 0.0,
                            saturation      = 120000., # JFH adjusted to this level as the flat are otherwise saturated
                            nonlinear       = 0.76,
                            numamplifiers   = 1,
                            gain            = 3.0,
                            ronoise         = 12.5,
                            oscansec        = '[1203:1232,:]',
                            suffix          = '_red'
                            )]
        # TODO: Can we change suffix to be unique wrt ShaneKastRed?
        self.numhead = 1
        # Uses timeunit from parent class
        # Uses default primary_hdrext
        # self.sky_file = ?

    def default_pypeit_par(self):
        """
        Set default parameters for Shane Kast Red Ret reductions.
        """
        par = ShaneKastSpectrograph.default_pypeit_par()
        par['rdx']['spectrograph'] = 'shane_kast_red_ret'
        par['calibrations']['pixelflatframe']['number'] = 3
        par['calibrations']['traceframe']['number'] = 3

        # 1D wavelength solution
        par['calibrations']['wavelengths']['lamps'] = ['NeI', 'HgI', 'HeI', 'ArI']
        par['calibrations']['wavelengths']['nonlinear_counts'] = self.detector[0]['nonlinear'] * self.detector[0]['saturation']
        par['calibrations']['wavelengths']['sigdetect'] = 5.

        return par

    def check_header(self, headers):
        """
        Check headers match expectations for a Shane Kast Red Ret
        exposure.

        See also
        :func:`pypeit.spectrographs.spectrograph.Spectrograph.check_headers`.

        Args:
            headers (list):
                A list of headers read from a fits file
        """
        expected_values = {   '0.NAXIS': 2,
                            '0.DSENSOR': 'Ret 400x1200' }
        super(ShaneKastRedRetSpectrograph, self).check_headers(headers,
                                                               expected_values=expected_values)
    
    def header_keys(self):
        """
        Header keys specific to shane_kast_red_ret

        Returns:

        """
        hdr_keys = super(ShaneKastRedRetSpectrograph, self).header_keys()
        hdr_keys[0]['dispname'] = 'GRATNG_N'
        hdr_keys[0]['filter1'] = 'RDFILT_N'
        hdr_keys[0]['dispangle'] = 'GRTILT_P'
        return hdr_keys

    def init_meta(self):
        """
        Meta data specific to shane_kast_blue

        Returns:

        """
        super(ShaneKastRedRetSpectrograph, self).init_meta()
        # Add the name of the dispersing element
        # dispangle and filter1 are not defined for Shane Kast Blue

        # Required
        self.meta['dispname'] = dict(ext=0, card='GRATNG_N')
        self.meta['dispangle'] = dict(ext=0, card='GRTILT_P')
        # Additional (for config)

