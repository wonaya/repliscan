import numpy as np
import argparse, os, re, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from itertools import izip_longest

# Didn't know how to handle EML and EL, so I'm treating distance as hamming to
# the inclusion
times = ('ES','ESMS','MS','MSLS','LS','ESLS','ESMSLS')
myColors = ("#2250F1","#28C5CC","#1A8A12","#FFFD33","#FB0018","#EA3CF2","#FAB427")
colorDict = dict(zip(times,myColors))
boolTimes = {'E':np.array((1,0,0),dtype=np.bool),'M':np.array((0,1,0),dtype=np.bool),'L':np.array((0,0,1),dtype=np.bool)}
timeRE = re.compile(r'Name=(([EML]S){1,3})')

def main():
	parser = argparse.ArgumentParser(description="Finds the timing differences between two segmentation profiles.")
	parser.add_argument("-d",metavar="INT", help="Minimum distance to be RAT (Default: %(default)s)", default=2, type=int)
	parser.add_argument("-S",metavar="INT", help="Tile Size (Default: %(default)s)", default=1000, type=int)
	parser.add_argument("-A",metavar="GFF3", help="First Segmentation Profile (mitotic)", required=True)
	parser.add_argument("-B",metavar="GFF3", help="Second Segmentation Profile (endo)", required=True)
	parser.add_argument("-F",metavar="FASTA", help="Reference", required=True)
	parser.add_argument("-O",metavar="BEDG", help="Output to bedgraph file", default=sys.stdout)
	parser.add_argument("--stats", action="store_true", help="Generate stats and figures")
	parser.add_argument("--fig",metavar="EXT", help="Figure type (Default: %(default)s)", default="pdf", type=str)
	args = parser.parse_args()
	if os.path.splitext(args.F)[1] in ['.fasta','.fa']:
		fai = args.F+'.fai'
	else:
		sys.exit("Please specify a fasta file\n")
	if args.stats and not args.O:
		sys.exit("Please specify an output bedgraph so stats are not hidden")
	chromDict = readFAI(fai)
	genomeA = processGenome(chromDict, args.S, args.A, args.stats, 'Mitotic', args.fig)
	genomeB = processGenome(chromDict, args.S, args.B, args.stats, 'Endocycle', args.fig)
	OF = open(args.O,'w')
	sortedChroms = sorted(chromDict.keys())
	X = [[] for i in xrange(len(sortedChroms))]
	if args.stats:
		for record in compareGenomes(genomeA, genomeB, chromDict, args.d, args.S, args.stats, args.fig):
			tmp = record.split('\t')
			size = int(tmp[2])-int(tmp[1])
			X[sortedChroms.index(tmp[0])].append(size)
			OF.write(record+'\n')
		plt.figure()
		plt.boxplot(X, labels=sortedChroms, showfliers=False)
		plt.ylabel("RAT size (bp)")
		plt.xlabel("Chromosome")
		plt.title("Size Distributions of RATs")
		plt.savefig("RAT_size."+args.fig)
		plt.close()
	else:
		for record in compareGenomes(genomeA, genomeB, chromDict, args.d, args.S, args.stats, args.fig):
			OF.write(record+'\n')
	OF.close()
	

def compareGenomes(A, B, chromDict, minD, tileSize, statsFlag, figExt):
	sortedChroms = sorted(chromDict.keys()[:])
	if statsFlag:
		fig, axes = plt.subplots(nrows=len(sortedChroms)+1)
		fig.subplots_adjust(top=0.95, bottom=0.05, left=0.07, right=0.97)
		axes[0].set_title("RAT Heatmap")
	for chrom, ax in zip(sortedChroms, axes):
		chromMA = A[chrom]
		chromMB = B[chrom]
		disps = map(dist, chromMA, chromMB)
		if statsFlag:
			if len(chromMA) < 600:
				Y = np.array([np.nanmean(i) for i in grouper(disps, np.ceil(len(disps)/30.0), fillvalue=0.0)])
			else:
				Y = np.array([np.nanmean(i) for i in grouper(disps, np.ceil(len(chromMA)/600.0), fillvalue=0.0)])
			Y = np.vstack((Y,Y))
			ax.imshow(Y, aspect='auto', cmap=plt.get_cmap("RdBu"), interpolation='nearest', vmin=-3, vmax=3)
			pos = list(ax.get_position().bounds)
			x_text = pos[0]-0.01
			y_text = pos[1] + pos[3]/2.0
			fig.text(x_text, y_text, chrom, va='center', ha='right', fontsize=10)
			ax.set_axis_off()
		oldRec = False
		for index in xrange(chromMA.shape[0]):
			displacement = disps[index]
			if abs(displacement) >= minD:
				if oldRec:
					if index == oldRec[1] and displacement == oldRec[2]:
						oldRec[1] = index+1
					else:
						s = oldRec[0]*tileSize
						e = min(chromDict[chrom], oldRec[1]*tileSize)
						yield("%s\t%i\t%i\t%i"%(chrom, s, e, oldRec[2]))
						oldRec = [index, index+1, displacement]
				else:
					oldRec = [index, index+1, displacement]
		if oldRec:
			s = oldRec[0]*tileSize
			e = min(chromDict[chrom], oldRec[1]*tileSize)
			yield("%s\t%i\t%i\t%i"%(chrom, s, e, oldRec[2]))
	if statsFlag:
		fig.text(0.03, 0.5, "Chromosome", va='center', ha='center', rotation='vertical')
		cb1 = matplotlib.colorbar.ColorbarBase(axes[-1], cmap=plt.get_cmap("RdBu"), norm=matplotlib.colors.Normalize(vmin=-3, vmax=3), orientation='horizontal')
		plt.savefig("RAT Plot."+figExt)

def grouper(iterable, n, fillvalue=None):
	"Collect data into fixed-length chunks or blocks"
	# grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
	args = [iter(iterable)] * n
	return izip_longest(*args, fillvalue=fillvalue)

def processGenome(chromDict, tileSize, gff, statsFlag, titleName, figExt):
	genome = makeGenomeStruct(chromDict, tileSize)
	updateGenomeStruct(genome, gff, tileSize, chromDict, statsFlag, titleName, figExt)
	return genome

def updateGenomeStruct(genome, gff, tileSize, chromDict, statsFlag, titleName, figExt):
	if statsFlag:
		segments = {chrom:[] for chrom in chromDict.keys()}
		for location, color in fileReader(gff):
			chrom = location[0]
			binArray = toBA(color)
			sI = np.ceil(location[1]/tileSize)
			eI = np.ceil(location[2]/float(tileSize))
			genome[chrom][sI:eI] = binArray
			segments[chrom].append((color, eI-sI))
		plotSize(segments, titleName, tileSize, figExt)
		plotComp(segments, titleName, tileSize, chromDict, figExt)
	else:
		for location, color in fileReader(gff):
			chrom = location[0]
			binArray = toBA(color)
			sI = np.ceil(location[1]/tileSize)
			eI = np.ceil(location[2]/float(tileSize))
			genome[chrom][sI:eI] = binArray

def plotComp(segments, titleName, tileSize, chromDict, figExt):
	plt.figure()
	yIndex = 0.1
	yHeight = 0.8
	sortedChroms = sorted(chromDict.keys())
	for chrom in sortedChroms:
		xranges = []
		chromSize = chromDict[chrom]
		X = np.zeros(len(times))
		for color, size in segments[chrom]:
			X[times.index(color)] += size*tileSize
		percents = list(np.round(X/float(chromSize),3))
		xranges += zip(np.cumsum([0]+percents[:-1]), percents)
		plt.broken_barh(xranges, (yIndex, yHeight), lw=0, color=myColors)
		yIndex += 1
	plt.xlim((0,1))
	plt.yticks(np.arange(0.5, len(sortedChroms)), sortedChroms)
	plt.ylabel("Chromosome")
	plt.xlabel("Fraction of Chromosome")
	plt.title(titleName+" Chromosome Composition")
	patches = [mpatches.Patch(color=myColors[i], label=times[i]) for i in xrange(len(times))]
	plt.figlegend(patches, times, loc='center right', ncol=1, frameon=False)
	plt.tight_layout(rect=[0,0,0.81,1.0])
	plt.savefig("composition_%s.%s"%(titleName, figExt))
	plt.close()

def plotSize(segments, titleName, tileSize, figExt):
	X = [[] for i in xrange(len(times))]
	for chromList in segments.itervalues():
		for color, size in chromList:
			X[times.index(color)].append(size*tileSize)
	print "%s Size Distribution"%(titleName)
	print "%-6s %10s %10s %10s %10s %10s %10s"%("","min","1st-Q","median","3rd-Q","max",'count')
	for segment in times:
		xIndex = times.index(segment)
		fiveSum = fivenum(X[xIndex]) # (min, 1st-Q, median, 3rd-Q, max)
		args = (segment,)+fiveSum+(len(X[xIndex]),)
		print "%-6s %10.1f %10.1f %10.1f %10.1f %10.1f %10i"%args
	plt.figure()
	plt.boxplot(X, labels=times, showfliers=False)
	plt.ylabel("Segment Size (bp)")
	plt.xlabel("Time")
	plt.title(titleName+" Size Distribution")
	plt.savefig("size_dist_%s.%s"%(titleName, figExt))
	plt.close()
		
def fileReader(a):
	if not os.path.splitext(a)[1] == '.gff3':
		sys.exit("%s is not a gff3 file"%(a))
	for line in open(a,'r'):
		if line[0] != '#':
			yield(lineParser(line)) #((chrom, start, end), color)

def lineParser(line):
	tmp = line.split('\t')
	location = (tmp[0], int(tmp[3])-1, int(tmp[4])) # (chrom, start, end)
	color = timeRE.search(tmp[8]).group(1) # color
	return location, color

def makeGenomeStruct(chromDict, tileSize):
	genome = {}
	for chrom, chromLen in chromDict.iteritems():
		numBins = np.ceil(chromLen/tileSize)
		genome[chrom] = np.zeros((numBins, 3), dtype=np.bool)
	return genome

def readFAI(inFile):
	'''
	Returns length of each chromosome in a dictionary.
	'''
	lineList = map(lambda x: x.rstrip('\n').split('\t'), open(inFile,'r').readlines())
	chromSizePairs = map(lambda x: (x[0],int(x[1])), lineList)
	return dict(chromSizePairs)

def dist(a,b):
	'''
	Calculates the shift of the index average between two binary arrays. If
	either of the arrays has no replication (all zero), the distance is
	returned as zero.

	   EML  index-mean	returned distance
	A: 110	0.5		1.5 - 0.5 = 1
	B: 011	1.5

	A: 001	2		1 - 2 = -1
	B: 010	1

	If the mean doesn't change, a distance of zero is returned instead. This will 
	only happen when moving between M, EL, and EML. This should be ok due to the
	low occurance of EL and EML in the results.

	   EML  index-mean	returned distance
	A: 101	1		0
	B: 010	1

	
	>>> dist(toBA('ESMS'),toBA('MSLS'))
	1
	>>> dist(toBA('LS'),toBA('MS'))
	-1
	>>> dist(toBA('ESLS'),toBA('MS'))
	0
	'''
	if np.sum(a) == 0 or np.sum(b) == 0:
		return 0
	indexMeanA = np.mean(np.where(a))
	indexMeanB = np.mean(np.where(b))
	return indexMeanB-indexMeanA

def toBA(a):
	'''
	>>> toBA('ESMS')
	array([ True,  True, False], dtype=bool)
	>>> toBA('MSLS')
	array([False,  True,  True], dtype=bool)
	'''
	return np.logical_or.reduce(map(lambda x: boolTimes[x], a.split('S')[:-1]))

def fivenum(v):
	'''
	Returns Tukey's five number summary

	(min, 1st-Q, median, 3rd-Q, max)

	for the input vector, a list or array of numbers based on 1.5 times
	the interquartile distance
	'''
	try:
		np.sum(v)
	except TypeError:
		print('Error: you must provide a list or array of only numbers')
	naV = np.array(v)
	notNAN = np.logical_not(np.isnan(naV))
	q1 = np.percentile(naV[notNAN],25)
	q3 = np.percentile(naV[notNAN],75)
	#iqd = q3-q1
	md = np.median(naV[notNAN])
	#whisker = 1.5*iqd
	return np.min(naV[notNAN]), q1, md, q3, np.max(naV[notNAN])

if __name__ == "__main__":
	main()
