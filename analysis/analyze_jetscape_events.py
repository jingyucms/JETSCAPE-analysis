#!/usr/bin/env python3

"""
  Class to analyze a JETSCAPE output files: do jet-finding and produce a ROOT file for each pt-hat bin.
  
  To run:
    python generate_jetscape_events.py -c ../config/jetscapeAnalysisConfig.yaml -o /my/outputdir
  
  The outputdir should contain the JETSCAPE output files in the structure generated by generate_jetscape_events.py.
  
  See README for pre-requisites.
  
  Author: James Mulligan (james.mulligan@berkeley.edu)
  """

from __future__ import print_function

# General
import os
import sys
import yaml
import argparse
import subprocess
import fileinput
import shutil

# Base class
import common_base

# Analysis
import jetscape_analysis
from reader import reader_hepmc
from reader import reader_ascii
import ROOT
import tqdm

################################################################
class analyze_jetscape_events(common_base.common_base):
  
  #---------------------------------------------------------------
  # Constructor
  #---------------------------------------------------------------
  def __init__(self, config_file='', input_file='', output_dir='', **kwargs):
    super(analyze_jetscape_events, self).__init__(**kwargs)
    self.config_file = config_file
    self.input_file = input_file
    self.output_dir = output_dir
    
    # Create output dir
    if not self.output_dir.endswith('/'):
      self.output_dir = self.output_dir + '/'
    if not os.path.exists(self.output_dir):
      os.makedirs(self.output_dir)
    
    self.initialize_config()
    
    print(self)

  #---------------------------------------------------------------
  # Initialize config file into class members
  #---------------------------------------------------------------
  def initialize_config(self):
    
    # Read config file
    with open(self.config_file, 'r') as stream:
      config = yaml.safe_load(stream)
    
    self.debug_level = config['debug_level']
    self.pt_hat_bins = config['pt_hat_bins']
    self.n_event_max = config['n_event_max']
    self.reader_type = config['reader']
    self.scale_histograms = config['scale_histograms']
    self.merge_histograms = config['merge_histograms']

  #---------------------------------------------------------------
  # Main processing function
  #---------------------------------------------------------------
  def analyze_jetscape_events(self):

    # Loop through pT-hat bins
    for bin, pt_hat_min in enumerate(self.pt_hat_bins):
      
      # Set min,max of pT-hat bin
      if bin < ( len(self.pt_hat_bins) -1 ):
        pt_hat_max = self.pt_hat_bins[bin+1]
        print('PtHat: {} - {}'.format(pt_hat_min, pt_hat_max))
      else:
        continue
      
      # Get outputDir for each bin
      output_dir_bin = '{}{}'.format(self.output_dir, bin)
      if not output_dir_bin.endswith('/'):
        output_dir_bin = output_dir_bin + '/'
      if not os.path.exists(output_dir_bin):
        print('output_dir_bin {} does not exist!'.format(bin))
      
      # Read HepMC output, get hadrons, do jet finding, and write histograms to ROOT file
      input_file = os.path.join(output_dir_bin, 'test_out.hepmc')
      self.run_jetscape_analysis(input_file, output_dir_bin, bin)
      
      # Scale histograms according to pthard bins cross-section
      if self.scale_histograms:
        print('Scaling pt-hat bins...')
        scaleHistograms.scaleHistograms(output_dir_bin, bin)
    
    # Merge all pthard bins into a single output file
    if self.merge_histograms:
      cmd = 'hadd {}AnalysisResultsFinal.root {}*/AnalysisResults.root'.format(self.output_dir, self.output_dir)
      subprocess.run(cmd, check=True, shell=True)

  #---------------------------------------------------------------
  # Main processing function for a single pt-hat bin
  #---------------------------------------------------------------
  def run_jetscape_analysis(self, input_file, output_dir_bin, bin):

    # Create reader class
    if self.reader_type == 'hepmc':
      reader = reader_hepmc.reader_hepmc(input_file)
    elif self.reader_type == 'ascii':
      reader = reader_ascii.reader_ascii(input_file)
    
    # Create analysis task
    analyzer = jetscape_analysis.jetscape_analysis(self.config_file, input_file, output_dir_bin, bin)

    # Initialize analysis output objects
    analyzer.initialize_output_objects()
  
    # Iterate through events
    pbar = tqdm.tqdm(range(self.n_event_max))
    for event in reader(n_events = self.n_event_max):
      
      if not event:
        nstop = pbar.n
        pbar.close()
        print('End of HepMC file at event {} '.format(nstop))
        break
      
      analyzer.analyze_event(event)
      pbar.update()

    # Write analysis task output to ROOT file
    analyzer.write_output_objects()

##################################################################
if __name__ == '__main__':
  # Define arguments
  parser = argparse.ArgumentParser(description='Generate JETSCAPE events')
  parser.add_argument('-c', '--configFile', action='store',
                      type=str, metavar='configFile',
                      default='/home/jetscape-user/JETSCAPE-analysis/config/jetscapeAnalysisConfig.yaml',
                      help="Path of config file for analysis")
  parser.add_argument('-o', '--outputDir', action='store',
                      type=str, metavar='outputDir',
                      default='/home/jetscape-user/JETSCAPE-analysis/TestOutput',
                      help='Output directory for output to be written to')
  
  # Parse the arguments
  args = parser.parse_args()
  
  # If invalid configFile is given, exit
  if not os.path.exists(args.configFile):
    print('File \"{0}\" does not exist! Exiting!'.format(args.configFile))
    sys.exit(0)
  
  # If invalid outputDir is given, exit
  if not os.path.exists(args.outputDir):
    print('File \"{0}\" does not exist! Exiting!'.format(args.outputDir))
    sys.exit(0)

  analysis = analyze_jetscape_events(config_file=args.configFile, output_dir=args.outputDir)
  analysis.analyze_jetscape_events()
