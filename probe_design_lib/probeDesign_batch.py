#!/usr/bin/env python3
from tiles import Tile, TileError
import probe_utils as utils
#import copy
#import string
from probe_utils import pp
import sequencelib
import repeatMask
import genomeMask
import HCR
#from probeDesign import BLAST
import sys,re
#from Bio.Seq import Seq
import primer3
from string import ascii_uppercase
import argparse
import pandas as pd
from itertools import product

#######################
# Scan input sequence #
#######################
#TODO: Modify this so that it only gets the window of appropriate size.  We will add prefix and suffix afterwards.

def scanSequence(sequence,seqName,tileStep=1,tileSize=52):
	tiles = []
	#Pre-compute number of chunks to emit
	numOfChunks = int(((len(sequence)-tileSize)/tileStep) + 1)

	#Tile across reverse complement of sequence
	for i in range(0,numOfChunks*tileStep,tileStep):
		tile = Tile(sequence=sequencelib.reverse_complement(sequence[i:i+tileSize]),seqName=seqName,startPos=i+1)
		if not tile.isMasked():
			tiles.append(tile)
	return tiles

###################
# Reporting
###################

def outputTable(tiles,outHandle=sys.stdout):
	"""
	Formats tile output and writes to outHandle
	"""
	outputKeys=["name","probe","start","length","P1","P2","channel","GC","Tm","dTm","GibbsFE"]
	outHandle.write("\t".join(outputKeys)+"\n")
	for tile in tiles:
		outHandle.write(f"{tile.name}\t{tile.sequence}\t{tile.start}\t{len(tile)}\t{tile.P1}\t{tile.P2}\t{tile.channel}\t{tile.GC():.2f}\t{primer3.calcTm(tile.sequence):.2f}\t{tile.dTm:.2f}\t{tile.Gibbs:.2f}\n")

def outputIDT(tiles,outHandle=sys.stdout):
	"""
	Formats tile output for direct ordering using IDT template
	"""
	#96-well addressing
	rows = list(ascii_uppercase[0:8])
	columns = [x+1 for x in range(12)]
	outputKeys = ["name","start","length","P1","P2","channel"]
	#Header for IDT plate template
	outHandle.write("\t".join(["Name","Sequence"])+"\n")
	#One row per oligo (P1='odd', P2='even')
	odd = []
	even = []
	for tile in tiles:
		odd.append((f"{tile.name}:{tile.channel}:odd",tile.P1))
		even.append((f"{tile.name}:{tile.channel}:even",tile.P2))
	
	for oligo in odd:
		outHandle.write(f"{oligo[0]}\t{oligo[1]}\n")
	
	for oligo in even:
		outHandle.write(f"{oligo[0]}\t{oligo[1]}\n")
		
		
#
# def alignOutput(inseq,tiles):
#     """Uses tile information to make a nice output w/ probes aligned to inseq
#
#     Returns 3 elements in a list:
#         [0] - the inseq
#         [1] - the oligos
#         [2] - probe # information
#     """
#     nTiles = len(tiles)
#     compoligos  = [seq.complement(inseq[j:(j+len(j))]) for j in tiles]
#     spaceoligos = [' '*(tiles[i]-tiles[i-1]-len(tiles[i])) for i in range(1,nTiles)]
#     spaceoligos = [' '*tiles[0]] + spaceoligos
#     probenum    = [ ('Probe # '+str(i+1)).ljust(len(tiles[i])) for i in range(nTiles)]
#
#     compseq  = ''.join([spaceoligos[i] + compoligos[i] for i in range(nTiles)])
#     probeseq = ''.join([spaceoligos[i] + probenum[i] for i in range(nTiles)])
#
#     compseq = compseq.ljust(len(inseq))
#     probeseq = probeseq.ljust(len(inseq))
#
#     return [inseq, compseq, probeseq]

def calcOligoCost(tiles,pricePerBase=0.19):
	total = 0.0
	for tile in tiles:
		probeSize = len(tile.P1) + len(tile.P2)
		total += probeSize*pricePerBase
	return total

def outputRunParams(args):
	utils.eprint(f"\nParameters:")
	utils.eprint(print(args))

def probe_design(mySeq, output, targetName = "target",verbose = True,species = 'mouse',genomemask = True,repeatmask = True,channel = "B1",num_hits_allowed = 1,maxProbes=100,dTmMax = 5.0,idt_output=False,calcPrice=True,tileStep = 1,maxRunLength=7, max_Th=50.0,numOverlap=5,minGC = 38.0, maxGC = 62.0,minGibbs = -70.0, maxGibbs = -50.0,checkProbeHairpin=True):
	
	"""
	Probe Design Utility for HCR v3.0. 
	file_path: Properly formatted fasta file against which to design probes
	output: 
	idt_output: 
	verbose: Verbose output
	channel: HCR Channel initiator sequences
	tileSize: Size of the tiles along the target sequence
	targetName: User-friendly name for target sequence (e.g. Gene Name)
	species: Species for repeatmask and genomemask
	minGC: Min allowable GC
	maxGC: Max allowable GC
	targetGC: Target GC
	dTmMax: Max allowable difference in Tm between probes in set
	dTmFilter: Enable filtering based on dTm between probeset halves
	genomemask: bowtie2 checking for multiple hits to genome
	index: Location of bowtie2 index file for genomemask analysis
	repeatmask: repeatmasker masking of target sequence
	maxProbes: Max number of probes to return
	maxRunMismatches: Max allowable homopolymer run mismatches
	num_hits_allowed: Number of allowable hits to genome
	idt_output: File name to output tsv format optimized for IDT ordering
	calcPrice: Calculate total cost of probe synthesis assuming $0.19 per base
	"""
	tileSize = 52
	# minGC = 35.0 # expose this parameter
	# maxGC = 65.0 # expose this parameter
	targetGC = 50.0
	targetGibbs = -60.0
	dTmFilter = False
	# maxRunLength=10 # expose this parameter
	maxRunMismatches=2
	# numOverlap=5 # expose this parameter
	# max_Th=50.0 # This is the maximum tolerated calculated melting temperature of any predicted hairpins 
	#########
	# Parse fasta file. Currently not looping over records, only uses first fasta record
	#########
	utils.eprint("Reading in Fasta file")
	# handle = open(file_path,'r')
	# fastaIter = sequencelib.FastaIterator(handle)
	outhandle=open(output, 'w')
	outhandle_idt=open(idt_output, 'w')
	# mySeq = next(fastaIter) #TODO: make loopable when migrating to main()

	#############
	# Repeatmask target sequence
	#############
	if repeatmask:
		# RepeatMasking
		utils.eprint(f"\nRepeat Masking using {species} reference...")
		mySeq['sequence'] = repeatMask.repeatmask(mySeq['sequence'],dnasource=species)

	# Check for invalid characters ?

	###############
	# Tile over masked sequence record to generate all possible probes of appropriate length that are not already masked
	###############
	utils.eprint(f"\nBreaking target sequence into revcomp tiles of size {tileSize}...")
	tiles = scanSequence(mySeq['sequence'],mySeq['name'],tileStep=tileStep,tileSize=tileSize) # Here we remove masked sequences and rev comp for tiles.
	utils.eprint(f'{len(tiles)} tiles available of length {tileSize}...')

	##############
	# Crunmask
	##############
	utils.eprint("\nChecking for runs of C's")
	tiles = [tile for tile in tiles if not tile.hasRuns(runChar='c',runLength=maxRunLength,mismatches=maxRunMismatches)]
	utils.eprint(f'{len(tiles)} tiles remain')

	##############
	# Grunmask
	##############
	utils.eprint("\nChecking for runs of G's")
	tiles = [tile for tile in tiles if not tile.hasRuns(runChar='g',runLength=maxRunLength,mismatches=maxRunMismatches)]
	utils.eprint(f'{len(tiles)} tiles remain')

	##############
	# Calculate Hairpins
	##############
	utils.eprint("\nChecking for hairpins")
	#TODO: add this as a user-selectable parameter. Currently awkward as we don't have a min Tm filter.
	tiles = [tile for tile in tiles if primer3.calcHairpin(tile.sequence).tm <= max_Th or not primer3.calcHairpin(tile.sequence).structure_found ]
	utils.eprint(f'{len(tiles)} tiles remain')

	##############
	# GenomeMasking?  Using bowtie because BLAST over WWW is unpredictable
	##############
	if genomemask:
		utils.eprint(f"\nChecking unique mapping of remaining tiles against {species} reference genome")
		blast_string = "\n".join([tile.toFasta() for tile in tiles])
		blast_res = genomeMask.genomemask(blast_string, handleName=targetName,species=species,index=None)
		utils.eprint(f'Parsing bowtie2 output now')
		hitCounts = genomeMask.countHitsFromSam(f'{targetName}.sam')
		#print(hitCounts)
		#Check that keys returned from hitCounts match order of tiles in tiles
		assert all(map(lambda x, y: x == y, [k for k in hitCounts.keys()], [tile.name for tile in tiles]))
		utils.eprint(f'Filtering for <= {num_hits_allowed} alignments to {species} genome...')
		for i in range(len(tiles)):
			k = list(hitCounts.keys())[i]
			tiles[i].hitCount = hitCounts[k]
			#utils.eprint(f'{tiles[i].hitCount}')
		tiles = [tile for tile in tiles if tile.hitCount <= num_hits_allowed]
		utils.eprint(f'{len(tiles)} tiles remain')

	###############
	# TM filtering
	###############

	###############
	# GC filtering
	###############
	utils.eprint(f"\nChecking for {minGC} < GC < {maxGC}")
	tiles = [tile for tile in tiles if tile.GC() >= minGC]
	tiles = [tile for tile in tiles if tile.GC() <= maxGC]
	utils.eprint(f'{len(tiles)} tiles remain')

	###############
	# Gibbs filtering
	###############
	utils.eprint(f"\nChecking for {minGibbs} < Gibbs FE < {maxGibbs}")
	[tile.calcGibbs() for tile in tiles]
	tiles = [tile for tile in tiles if tile.Gibbs >= minGibbs]
	tiles = [tile for tile in tiles if tile.Gibbs <= maxGibbs]
	utils.eprint(f'{len(tiles)} tiles remain')

	###############
	# Split tile into probeset
	###############
	utils.eprint(f"\nSplitting tiles into probesets")
	[tile.splitProbe() for tile in tiles]
	[tile.calcdTm() for tile in tiles]

	###############
	# dTm between halves
	###############
	if dTmFilter:
		utils.eprint(f"\nChecking for dTm <= {dTmMax} between probes for each tile")
		tiles = [tile for tile in tiles if tile.dTm <= dTmMax]
		utils.eprint(f'{len(tiles)} tiles remain')

	###############
	# Break remaining probes into non-overlapping regions
	###############
	# #TODO: there must be a better way to do this to minimize overlaps.  Perhaps testing overlaps from bestTiles later on?  Would ensure better quality picks make it to the end.
	# regions = {}
	# regionCount = 0
	#
	# regionList = [tiles[0]]
	# for i in range(1,len(tiles)):
	# 	if i == len(tiles)-1:
	# 		regions[ascii_uppercase[regionCount]] = regionList
	# 		break
	# 	if tiles[i].overlaps(tiles[i-1]):
	# 		regionList.append(tiles[i])
	# 	else:
	# 		regions[ascii_uppercase[regionCount]] = regionList
	# 		regionList = [tiles[i]]
	# 		regionCount = regionCount + 1
	#
	# ################
	# # Select best from each region
	# ################
	# bestTiles = []
	# for k,v in regions.items():
	# 	bestTiles.append(v[min(range(len(v)), key=lambda i: abs([x.Gibbs for x in v][i]-targetGibbs))])

	################
	# Select overall best n tiles (regardless of region)
	################
	# Instead of above 'region-based' approach, Let's start by choosing the best probes (by min distance to targetGibbs and/or min distance to targetGC).
	# As we choose subsequent best probes, test for overlap (greater than numOverlap nt) with any existing tiles (tile.overlaps(tile2)).  If none, then append next best to bestTiles
	# Do this until you are out of tiles or bestTiles reaches a certain number of tiles.

	#TODO: Currently ranking tiles based on min distance to targetGibbs.  Need to make an argument to select targetGC as goal instead.
	bestTiles = []
	while len(tiles) > 0:
		nextBestIdx = min(range(len(tiles)), key=lambda i: abs([x.Gibbs for x in tiles][i]-targetGibbs))
		# print(f'{nextBestIdx}')
		if len(bestTiles) == 0:
			bestTiles.append(tiles.pop(nextBestIdx))
			continue
		if any([tiles[nextBestIdx].overlaps(x, numOverlap) for x in bestTiles]):
			tiles.pop(nextBestIdx)
		else:
			bestTiles.append(tiles.pop(nextBestIdx))
			
	utils.eprint(f'{len(bestTiles)} tiles remain after removing tiles that have greater than {numOverlap}nt overlap')
	
	################
	# Add initator and spacers to split probes
	################
	utils.eprint(f"\nAdding spacers and initiator sequences to split probes for channel {channel.name}")
	[tile.makeBarcode(channel) for tile in bestTiles]

	if checkProbeHairpin:
		finalTiles = []
		for tile in bestTiles:
			if primer3.calcHairpin(tile.P1).tm <= max_Th or not primer3.calcHairpin(tile.P1).structure_found:
				if primer3.calcHairpin(tile.P2).tm <= max_Th or not primer3.calcHairpin(tile.P2).structure_found:
					finalTiles.append(tile)
	else:
		finalTiles=bestTiles
	
	finalTiles=finalTiles[:maxProbes]

	utils.eprint(f'Selected {len(finalTiles)} tiles after checking hairpins again')

	outputTable(finalTiles,outHandle=outhandle)
	################
	# Print out results
	################
	# for tile in bestTiles:
	# 	print(f"{tile}\tP1_sequence:{tile.P1}\tP2_sequence:{tile.P2}\tmyTm:{tile.Tm():.2f}\tprimer3-Tm:{primer3.calcTm(tile.sequence):.2f}\tdTm:{tile.dTm:.2f}\tGC%:{tile.GC():.2f}\tGibbs:{tile.Gibbs:.2f}")
	if calcPrice:
		utils.eprint(f'\nTotal cost to synthesize probe sets ~${calcOligoCost(finalTiles):.2f}')
	
	if idt_output is not None:
		outputIDT(finalTiles,outHandle=outhandle_idt)
	
	return finalTiles, len(finalTiles)
