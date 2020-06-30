#!/usr/bin/env python3

""" Class to analyze a JETSCAPE output files: do jet-finding and produce a ROOT file for each pt-hat bin.

To run: generateJetscape -c ../config/jetscapeAnalysisConfig.yaml -o /my/outputdir

The outputdir should contain the JETSCAPE output files in the structure generated by generate_jetscape_events.py.

See README for pre-requisites.

.. codeauthor:: James Mulligan <james.mulligan@berkeley.edu>, UC Berkeley
"""

from __future__ import print_function

import os
import subprocess
import sys

# Analysis
import tqdm
import yaml
import itertools
import ROOT

from jetscape_analysis.analysis import scale_histograms
from jetscape_analysis.analysis.reader import reader_ascii, reader_hepmc
from jetscape_analysis.base import common_base

################################################################
class AnalyzeJetscapeEvents_Base(common_base.CommonBase):

    # ---------------------------------------------------------------
    # Constructor
    # ---------------------------------------------------------------
    def __init__(self, config_file="", input_dir="", output_dir="", **kwargs):
        super(AnalyzeJetscapeEvents_Base, self).__init__(**kwargs)
        self.config_file = config_file
        self.input_dir = input_dir
        self.output_dir = output_dir

        if not self.input_dir.endswith("/"):
            self.input_dir = self.input_dir + "/"

        # Create output dir
        if not self.output_dir.endswith("/"):
            self.output_dir = self.output_dir + "/"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        self.initialize_config()

    # ---------------------------------------------------------------
    # Initialize config file into class members
    # ---------------------------------------------------------------
    def initialize_config(self):

        # Read config file
        with open(self.config_file, 'r') as stream:
            config = yaml.safe_load(stream)
            
        self.parameter_scan_dict = config['parameter_scan']
        self.pt_hat_bins = self.parameter_scan_dict['pt_hat_bins']['values']
        self.n_pt_hat_bins = len(self.parameter_scan_dict['pt_hat_bins']['values']) - 1

        self.debug_level = config['debug_level']
        self.n_event_max = config['n_event_max']
        self.reader_type = config['reader']
        if self.reader_type == 'ascii':
            self.reader_type = 'dat'
        self.progress_bar = config['progress_bar']
        self.scale_histograms = config['scale_histograms']
        self.merge_histograms = config['merge_histograms']
        
        self.event_id = 0

    # ---------------------------------------------------------------
    # Main processing function
    # ---------------------------------------------------------------
    def analyze_jetscape_events(self):
    
        # Store list of parameter labels
        parameter_labels = [self.parameter_scan_dict[key]['label'] for key in self.parameter_scan_dict]

        # Create list of all combinations of parameters
        parameter_values = [self.parameter_scan_dict[key]['values'] for key in self.parameter_scan_dict]
        parameter_combinations = list(itertools.product(*parameter_values))
    
        # Remove that last pt-hat bin edge
        n_combinations_per_pthat = int(len(parameter_combinations)/len(self.pt_hat_bins))
        parameter_combinations = parameter_combinations[:-n_combinations_per_pthat]

        # Loop through all parameter combinations
        for index, parameter_combination in enumerate(parameter_combinations):
        
            self.pt_hat_bin = int(index / n_combinations_per_pthat)
            if self.pt_hat_bin < len(self.pt_hat_bins) - 1:
                pt_hat_min = self.pt_hat_bins[self.pt_hat_bin]
                pt_hat_max = self.pt_hat_bins[self.pt_hat_bin + 1]
            else:
                continue
            if index % n_combinations_per_pthat == 0:
                print('Analyzing pt-hat: {} - {} ...'.format(pt_hat_min, pt_hat_max))

            # Create label for output directory
            dir_label = ''
            for index, value in enumerate(parameter_combination):
                if index == 0:
                    dir_label += str(self.pt_hat_bin)
                    continue
                dir_label += '_'
                dir_label += parameter_labels[index]
                dir_label += str(value)
            if len(parameter_combination) > 1:
                print('    Analyzing {}'.format(dir_label))
                
            # Create outputDir for each bin
            self.output_dir_bin = '{}{}'.format(self.output_dir, dir_label)
            if not self.output_dir_bin.endswith("/"):
                self.output_dir_bin = self.output_dir_bin + "/"
            if not os.path.exists(self.output_dir_bin):
                os.makedirs(self.output_dir_bin)
    
            # Read JETSCAPE output, get hadrons, do jet finding, and write histograms to ROOT file
            input_dir_bin = '{}{}'.format(self.input_dir, dir_label)
            self.input_file = os.path.join(input_dir_bin, 'test_out.{}'.format(self.reader_type))
            self.run_jetscape_analysis()

            # Scale histograms according to pthard bins cross-section
            if self.scale_histograms:
                print("Scaling pt-hat bins...")
                scale_histograms.scale_histograms(self.output_dir_bin, self.pt_hat_bin, bRemoveOutliers=False)

        # Merge all pthard bins into a single output file
        if self.merge_histograms:
            cmd = "hadd {}AnalysisResultsFinal.root {}*/AnalysisResults.root".format(self.output_dir, self.output_dir)
            subprocess.run(cmd, check=True, shell=True)

    # ---------------------------------------------------------------
    # Main processing function for a single pt-hat bin
    # ---------------------------------------------------------------
    def run_jetscape_analysis(self):

        # Create reader class
        if self.reader_type == 'hepmc':
            self.reader = reader_hepmc.ReaderHepMC(self.input_file)
        elif self.reader_type == 'dat':
            self.reader = reader_ascii.ReaderAscii(self.input_file)

        # Initialize output objects
        self.initialize_output_objects()

        # Iterate through events
        if self.progress_bar:
            pbar = tqdm.tqdm(range(self.n_event_max))
        for event in self.reader(n_events=self.n_event_max):

            if not event:
                if self.progress_bar:
                    nstop = pbar.n
                    pbar.close()
                    print('End of {} file at event {} '.format(self.reader_type, nstop))
                else:
                    print('End of {} file.'.format(self.reader_type))
                break

            # Print and store basic event info
            self.get_event_info(event)
            
            # Call user-defined function to analyze event
            self.analyze_event(event)
            if self.progress_bar:
                pbar.update()

        # Write analysis task output to ROOT file
        self.write_output_objects()

    # ---------------------------------------------------------------
    # Initialize output objects
    # ---------------------------------------------------------------
    def initialize_output_objects(self):

        # Event histograms
        self.hNevents = ROOT.TH1F('hNevents', 'hNevents', self.n_pt_hat_bins, 0, self.n_pt_hat_bins)
        self.hCrossSection = ROOT.TH1F('hCrossSection', 'hCrossSection', self.n_pt_hat_bins, 0, self.n_pt_hat_bins)
        
        # Initialize user-defined output objects
        self.initialize_user_output_objects()
        
    # ---------------------------------------------------------------
    # Get event info
    # ---------------------------------------------------------------
    def get_event_info(self, event):

        # Print some basic info for first event
        #if self.event_id == 0:

            # Get heavy ion attributes
            #heavy_ion = event.heavy_ion()
            # However it seems that pyhepmc_ng doesn't implement any of these...
            #print(dir(heavy_ion))
            #nColl = heavy_ion.Ncoll
            #nPart = heavy_ion.Npart_proj
            #eventPlaneAngle = heavy_ion.event_plane_angle
            #print('NColl = {}, NPart = {}, EP-angle = {}'.format(nColl, nPart, eventPlaneAngle))

        self.event_id += 1

    # ---------------------------------------------------------------
    # Save all ROOT histograms and trees to file
    # ---------------------------------------------------------------
    def write_output_objects(self):

        # Fill cross-section with last event's value, which is most accurate
        xsec = self.cross_section()
        self.hCrossSection.SetBinContent(self.pt_hat_bin+1, xsec)
        
        # Set N events
        self.hNevents.SetBinContent(self.pt_hat_bin+1, self.event_id)

        # Save output objects
        outputfilename = os.path.join(self.output_dir_bin, 'AnalysisResults.root')
        fout = ROOT.TFile(outputfilename, 'recreate')
        fout.cd()
        for attr in dir(self):

            obj = getattr(self, attr)

            # Write all ROOT histograms and trees to file
            types = (ROOT.TH1, ROOT.THnBase, ROOT.TTree)
            if isinstance(obj, types):
                obj.Write()
                obj.SetDirectory(0)
                del obj

        fout.Close()
        
    # ---------------------------------------------------------------
    # Get cross-section from last event JETSCAPE output file
    #
    # It seems that pyhepmc_ng doesn't contain GenCrossSection, so we need to find it manually
    # Similarly, we find the cross-section manually for ascii format.
    # ---------------------------------------------------------------
    def cross_section(self):
        
        # Fill array of cross-sections
        cross_sections = []
        with open(self.input_file, 'r') as infile:
            for line in infile:
            
                if self.reader_type == 'hepmc':
                    if 'GenCrossSection' in line:
                        split = line.split()
                        xsec = float(split[3]) / 1e9
                        cross_sections.append(xsec)
            
                elif self.reader_type == 'dat':
                    if 'sigmaGen' in line:
                        split = line.split()
                        xsec = float(split[2])
                        cross_sections.append(line)
                        
        # Return cross-section with last event's value, which is most accurate
        return cross_sections[-1]

    # ---------------------------------------------------------------
    # This function is called once per setting
    # You must implement this
    # ---------------------------------------------------------------
    def initialize_user_output_objects(self):
        raise NotImplementedError('You must implement initialize_user_output_objects()!')
        
    # ---------------------------------------------------------------
    # This function is called once per event (per setting)
    # You must implement this
    # ---------------------------------------------------------------
    def analyze_event(self, event):
        raise NotImplementedError('You must implement analyze_event()!')
