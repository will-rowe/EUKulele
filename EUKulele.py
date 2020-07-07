#!/usr/bin/env python

# Software for taxonomic identification of eukaryotes.

import pandas as pd
import numpy as np
import os
import sys
import yaml
import chardet
import argparse
import multiprocessing
import subprocess
import shutil
from joblib import Parallel, delayed
sys.path.insert(1, 'scripts')

import tax_placement
from tax_placement import *

import query_busco
from query_busco import *

import visualize_results
from visualize_results import *

__author__ = "Harriet Alexander, Arianna Krinos"
__copyright__ = "EUKulele"
__license__ = "MIT"
__email__ = "akrinos@mit.edu"

## FUNCTIONS TO USE IN PIPELINE ##

def transdecode_to_peptide(sample_name):
    if os.path.isfile(os.path.join(OUTPUTDIR, "METs",  "{T}." + PEP_EXT)):
        print("TransDecoder file already detected; will not re-run step.")
        return 0
    p1 = subprocess.Popen(["TransDecoder.LongOrfs -t " + os.path.join(SAMPLE_DIR, "METs", sample_name + "." + NT_EXT) + " -m " + " 2> " + os.path.join("logs", "trandecoder_error_" + sample_name + ".out") + " 1> " + os.path.join("logs", "trandecoder_out_" + sample_name + ".out")])
    p1.wait()
    rc1 = p1.returncode
    p2 = subprocess.Popen(["TransDecoder.Predict -t " + os.path.join(SAMPLE_DIR, "METs", sample_name + "." + NT_EXT) + " --no_refine_starts 2>> " + os.path.join("logs", "trandecoder_error_" + sample_name + ".out") + " 1>> " + os.path.join("logs", "trandecoder_out_" + sample_name + ".out")])
    p2.wait()
    rc2 = p2.returncode
    os.replace(merged_name + ".transdecoder.pep", os.path.join(OUTPUTDIR, "METs",  "{T}." + PEP_EXT))
    os.replace(merged_name + ".transdecoder.cds", os.path.join(OUTPUTDIR, "METs", "transdecoder", "{T}.fasta.transdecoder.bed"))
    os.replace(merged_name + ".transdecoder.gff3", os.path.join(OUTPUTDIR, "METs", "transdecoder", "{T}.fasta.transdecoder.gff3"))
    os.replace(merged_name + ".transdecoder.bed", os.path.join(OUTPUTDIR, "METs", "transdecoder", "{T}.fasta.transdecoder.bed"))
    os.remove(glob.glob("pipeliner*"))
    shutil.rmtree(shutil.rmtree(merged_name + ".transdecoder_dir*"))
    return rc1 + rc2

def align_to_database(alignment_choice, sample_name):
    if alignment_choice == "diamond":
        diamond_out = os.path.join(OUTPUTDIR, "METs", "diamond", sample_name + ".diamond.out")
        if os.path.isfile(diamond_out):
            print("Diamond alignment file already detected; will not re-run step.")
            return 0
        
        align_db = os.path.join(DATABASE_DIR, "diamond", REF_FASTA.strip('.fa') + '.dmnd')
        fasta = os.path.join(OUTPUTDIR, "METs", sample_name + "." + PEP_EXT) 
        other = "--outfmt 6 -k 100 -e 1e-5"
        outfmt = 6
        k = 100
        e = 1e-5
        p1 = subprocess.Popen(["diamond blastp --db " + align_db + " -q " + {input.fasta} + " -o " + diamond_out + " --outfmt " + str(outfmt) + " -k " + str(k) + " -e " + str(e)])
        p1.wait()
        rc1 = p1.returncode
        if rc1 != 0:
            print("Diamond did not complete successfully.")
            return 1
        return diamond_out
    else:
        blast_out = os.path.join(OUTPUTDIR, "METs", "blast", sample_name + ".blast.txt")
        if os.path.isfile(blast_out):
            print("BLAST alignment file already detected; will not re-run step.")
            return 0
        align_db = os.path.join(DATABASE_DIR, "blast", REF_FASTA.strip('.fa'), "database")
        fasta = os.path.join(OUTPUTDIR, "METs", "{T}." + PEP_EXT) 
        outfmt = 6 # tabular output format
        e = 1e-5
        os.system("export BLASTDB=" + align_db)
        p1 subprocess.Popen(["blastp -query " + align_db + " -db " + align_db + " -out " + blast_out + " -outfmt " + str(outfmt) + " -evalue " + str(e)])
        p1.wait()
        rc1 = p1.returncode
        if rc1 != 0:
            print("BLAST did not complete successfully.")
            return 1
        return blast_out

parser = argparse.ArgumentParser()
parser.add_argument('--mets_or_mags', required = True) 
parser.add_argument('--nucleotide_extension', default = ".fasta") 
parser.add_argument('--protein_extension', default = ".faa") 
parser.add_argument('--scratch', default = '../scratch') # the scratch location to store intermediate files

## SALMON OPTIONS ##
parser.add_argument('--use_salmon_counts', type = int, default = 0)
parser.add_argument('--salmon_dir') # salmon directory is required if use_salmon_counts is true.
parser.add_argument('--names_to_reads',default=0) # a file to be created or used if it exists that relates transcript names to salmon counts from the salmon directory 

## WHERE FILES ARE LOCATED ##
parser.add_argument('--database', required = True) # the name of the database to be used to assess the reads
parser.add_argument('--reference_dir', required = True) # folder containing the reference files for the chosen database
parser.add_argument('-o','--out_dir', dest = "out_dir", required = True) # folder where the output will be written
parser.add_argument('--sample_dir', required = True) # folder where the input data is located (the protein or peptide files to be assessed)
parser.add_argument('--ref_fasta', required = True) # either a file in the reference directory where the fasta file for the database is located, or a directory containing multiple fasta files that constitute the database.
parser.add_argument('--ref_fasta_ext', default = ".fasta") # if a directory is given for ref_fasta and the extension of the files differs from .fasta, specify it via this argument.

## TAXONOMY TABLE AND PROTEIN JSON FILE ## 
parser.add_argument('--create_tax_table', action='store_true') # include this file if you wish for the protein dictionary file and the taxonomy table to be created from the reference fasta(s) that you have provided. Otherwise, these files should be called "tax-table.txt" and "protein-map.json" and should be located in your reference_dir, unless specified via the below flags.
parser.add_argument('--original_tax_table', default = "", type = str) # this is required if you have specified "create_tax_table"
parser.add_argument('--strain_col_id',  type=str, default = 'strain_name') # the column which indicates the name of the strain in the taxonomy file
parser.add_argument('--taxonomy_col_id',  type=str, default = 'taxonomy') # the column which indicates the taxonomy of the strain in the taxonomy file
parser.add_argument('--column', type=str, default = 'SOURCE_ID') # can be numeric, zero-indexed, if it's a delimited part of header
# set to true if there is a column called "taxonomy" that we wish to split
parser.add_argument('--reformat_tax', dest='reformat', default=False, action='store_true') 

parser.add_argument('--delimiter', default = "/", type = str)
parser.add_argument('--tax_table', default = "tax-table.txt")
parser.add_argument('--protein_map', default = "protein-map.json")

## ALIGNMENT OPTIONS ##
parser.add_argument('--alignment_choice', default = "diamond", choices = ["diamond", "blast"])

## OPTIONS FOR CHECKING BUSCO COMPLETENESS FOR TAXONOMY ##
parser.add_argument('--busco_file', default = "", type = str) # if specified, the following two arguments ("--organisms" and "--taxonomy_organisms" are overwritten by the two columns of this tab-separated file
parser.add_argument('--organisms', default = "", type = list, narg = "+") # list of organisms to check BUSCO completeness on
parser.add_argument('--taxonomy_organisms', default = "", type = list, narg = "+") # taxonomic level of organisms specified in organisms tag

## OTHER USER CHOICES ## 
parser.add_argument('--cutoff', default = "static/tax-cutoffs.yaml")
parser.add_argument('--cutoff_metric', default = "pid", choices = ["pid", "evalue"])
parser.add_argument('--consensus_cutoff', default = 0.75, type = float)
parser.add_argument('--transdecoder_orfsize', default = 100, type = int)

parser.add_argument('--CPUs', default=1)
parser.add_argument('-p', action='store_true') # whether to run in parallel
parser.add_argument('--busco_threshold', default=50)

args = parser.parse_args()

## VARIABLES ##
CONSENSUS_CUTOFF = args.consensus_cutoff
REFERENCE_DIR = args.reference_dir
OUTPUTDIR = args.out_dir
DATABASE_DIR = os.path.join(REFERENCE_DIR, "database")
SAMPLE_DIR = args.sample_dir
REF_FASTA = args.ref_fasta
TAX_TAB = os.path.join(REFERENCE_DIR, args.tax_table)
PROT_TAB = os.path.join(REFERENCE_DIR, args.protein_map)
ALIGNMENT_CHOICE = config['alignment_choice']
IFPARALLEL = config['choose_parallel']
OUTPUT_EXTENSION = "txt"
DBEXTENSION = ""
TRANSDECODERORFSIZE=config['transdecoder_orfsize']
if ALIGNMENT_CHOICE == "diamond":
    OUTPUT_EXTENSION = "out"
    DBEXTENSION = ".dmnd"
NT_EXT = config['nucleotide_extension'].strip('.')
PEP_EXT = config['protein_extension'].strip('.')
mets_or_mags=config['mets_or_mags'].lower()
USE_SALMON_COUNTS = config["use_salmon_counts"]
SALMON_DIR = config["salmon_dir"]
NAMES_TO_READS = os.path.join(REFERENCE_DIR, config["names_to_reads"])

ORGANISMS = args.organisms
ORGANISMS_TAXONOMY = args.organisms_taxonomy
BUSCO_FILE = args.busco_file
if (BUSCO_FILE != "") & (os.path.isfile(BUSCO_FILE)):
    busco_file_read = read.csv(BUSCO_FILE, sep = "\t")
    ORGANISMS = list(busco_file_read.iloc[:,0])
    ORGANISMS_TAXONOMY = list(busco_file_read.iloc[:,1])
    print("Organisms and their taxonomy levels for BUSCO analysis were read from file.")
else:
    print("No BUSCO file specified/found; using argument-specified organisms and taxonomy for BUSCO analysis.")

if (len(ORGANISMS) != len(ORGANISMS_TAXONOMY)):
    print("Organisms and taxonomic specifications for BUSCO analysis do not contain the same number of entries. Please revise such that each organism flagged for BUSCO analysis also includes its original taxonomic level.")
    sys.exit(1)

## SETUP STEPS ##
if args.create_tax_table:
    if args.original_tax_table == "":
        print("You must provide a taxonomy table via the argument 'original_tax_table' if you wish to run a taxonomy.")
        sys.exit(1)
    eukprot = ""
    if args.database == "eukprot":
        eukprot = " --euk-prot "
    p1 = subprocess.Popen(["python scripts/create_protein_table --infile_peptide " + REF_FASTA + " --infile_taxonomy " + args.original_tax_table + " --output " + TAX_TAB  + " --outfile_json " + PROT_TAB + " --delim " + args.delimiter + " --strain_col_id " + args.strain_col_id + " --taxonomy_col_id " + args.taxonomy_col_id + " --column " + args.column + " --reformat_tax " + args.reformat + eukprot])
    p1.wait()
    
## Concatenate potential list of input FASTA files ##
space_delim = " ".join(REFERENCE_FASTAS)
concatenated_file = os.path.join(OUTPUTDIR, "concatfasta.fasta")
p1 = subprocess.Popen(["for currfile in " + space_delim + "; do ((cat $currfile | sed 's/\./N/g'); echo; echo) >> " + concatenated_file + "; done"])
p1.wait()

if args.alignment_choice == "diamond":
    ## DIAMOND database creation ##
    db = os.path.join(DATABASE_DIR, "diamond", REF_FASTA.strip('.fa'))
    p1 = subprocess.Popen(["diamond makedb --in " + concatenated_file + " --db " + db])
    p1.wait()
else:
    db = os.path.join(DATABASE_DIR, "blast", REF_FASTA.strip('.fa'), "database")
    db_type = "prot"
    blast_version = 5
    p1 = subprocess.Popen(["makeblastdb -in " + concatenated_file + " -parse_seqids -blastdb_version " + str(blast_version) + " -title " + args.database + " -dbtype " + db_type + " -out " + db])
    p1.wait()
    
## Now for some TransDecoding ##
MTS, = glob_wildcards(os.path.join(SAMPLE_DIR, "METs", "{T}"+ "." + NT_EXT)) 
MAG, = glob_wildcards(os.path.join(SAMPLE_DIR, "MAGs", "{G}"+ "." + PEP_EXT))

transdecoder_res = Parallel(n_jobs=multiprocessing.cpu_count())(delayed(transdecode_to_peptide)(sample_name) for sample_name in MTS)
all_codes = sum(transdecoder_res)
if all_codes > 0:
    print("TransDecoder did not complete successfully; check log folder for details.")
    sys.exit(1)
    
## Next to align against our database of choice ##
alignment_res = Parallel(n_jobs=multiprocessing.cpu_count())(delayed(align_to_database)(args.alignment_choice, sample_name) for sample_name in MTS)
if any([curr == 1 for curr in alignment_res]):
    print("Alignment did not complete successfully.")
    sys.exit(1)
       
## Next to do taxonomy estimation ##
if (USE_SALMON_COUNTS == 1):
    p1 = subprocess.Popen(["python scripts/names-to-reads.py"])
    p1.wait()
    
outfiles = [os.path.join(OUTPUTDIR, "METs", samp + "-estimated-taxonomy.out") for samp in MTS]
taxonomy_res = Parallel(n_jobs=multiprocessing.cpu_count())(delayed(place_taxonomy)(TAX_TAB,args.cutoff,CONSENSUS_CUTOFF,PROT_TAB,USE_SALMON_COUNTS,NAMES_TO_READS,alignment_res[t],outfiles[t],IFPARALLEL) for t in range(len(alignment_res)))

## Now to visualize the taxonomy ##
out_prefix = OUTPUTDIR.split("/")[-1]
visualize_all_results(out_prefix, OUTPUTDIR, os.path.join(OUTPUTDIR, "METs"), os.path.join(OUTPUTDIR, "METs"), PEP_EXT, NT_EXT, USE_SALMON_COUNTS)

