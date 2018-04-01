import os

import numpy as np
import pyBigWig
import pysam
from HTSeq import GenomicInterval

from janggo.data.data import Dataset
from janggo.data.genomic_indexer import GenomicIndexer
from janggo.data.genomicarray import create_genomic_array


class CoverageDataset(Dataset):
    """CoverageDataset class.

    This datastructure holds coverage information across the genome.
    The coverage can conveniently fetched from a bam-file, a bigwig-file,
    or a list of files. E.g. a list of bam-files.
    For convenience, the

    Parameters
    -----------
    name : str
        Name of the dataset
    covers : :class:`BlgGenomicArray`
        A genomic array that holds the coverage data
    gindxer : :class:`GenomicIndexer`
        A genomic index mapper that translates an integer index to a
        genomic coordinate.
    flank : int
        Number of flanking regions to take into account. Default: 4.
    stranded : boolean
        Consider strandedness of coverage. Default: True.


    Attributes
    -----------
    name : str
        Name of the dataset
    covers : :class:`BlgGenomicArray`
        A genomic array that holds the coverage data
    gindxer : :class:`GenomicIndexer`
        A genomic index mapper that translates an integer index to a
        genomic coordinate.
    flank : int
        Number of flanking regions to take into account. Default: 4.
    stranded : boolean
        Consider strandedness of coverage. Default: True.

    """

    _flank = None

    def __init__(self, name, covers,
                 gindexer,  # indices of pointing to region start
                 flank=4,  # flanking region to consider
                 stranded=True):  # strandedness to consider

        self.covers = covers
        self.gindexer = gindexer
        self.flank = flank
        self.stranded = stranded

        Dataset.__init__(self, '{}'.format(name))

    @classmethod
    def create_from_bam(cls, name, bamfiles, regions, genomesize=None,
                        samplenames=None,
                        min_mapq=None,
                        binsize=50, stepsize=50,
                        flank=150, storage='hdf5',
                        dtype='int',
                        overwrite=False,
                        cachedir=None):
        """Create a CoverageDataset class from a bam-file (or files).

        Parameters
        -----------
        name : str
            Name of the dataset
        bamfiles : str or list
            bam-file or list of bam files.
        gindxer : pandas.DataFrame or str
            bed-filename or content of a bed-file
            (in terms of a pandas.DataFrame).
        genomesize : dict
            Dictionary containing the genome size.
        samplenames : list
            List of samplenames. Default: None means that the filenames
            are used as samplenames as well.
        binsize : int
            Binsize in basepairs. Default: 50.
        stepsize : int
            Stepsize in basepairs. This defines the step size for traversing
            the genome. Default: 50.
        flank : int
            Adjacent flanking size to extend in basepairs. Default: 150.
        stranded : boolean
            Consider strandedness of coverage. Default: True.
        storage : str
            Storage mode for storing the coverage data can be
            'step', 'ndarray', 'memmap' or 'hdf5'. Default: 'hdf5'.
        overwrite : boolean
            overwrite cachefiles. Default: False.
        cachedir : str or None
            Directory in which the cachefiles are located. Default: None.
        """

        gindexer = GenomicIndexer.create_from_file(regions, binsize, stepsize)

        if isinstance(bamfiles, str):
            bamfiles = [bamfiles]

        if not samplenames:
            samplenames = bamfiles

        if not min_mapq:
            min_mapq = 0

        if not genomesize:
            header = pysam.AlignmentFile(bamfiles[0], 'r')
            genomesize = {}
            for chrom, length in zip(header.references, header.lengths):
                genomesize[chrom] = length

        def bam_loader(cover, files):
            print("load from bam")
            for i, sample_file in enumerate(files):
                print('Counting from {}'.format(sample_file))
                aln_file = pysam.AlignmentFile(sample_file, 'rb')
                for chrom in genomesize:

                    array = np.zeros((genomesize[chrom], 2), dtype=dtype)

                    try:
                        it_ = aln_file.fetch(chrom)
                    except ValueError:
                        print("Contig '{}' abscent in bam".format(chrom))
                        continue
                    for aln in it_:
                        if aln.mapq < min_mapq:
                            continue

                        if aln.is_reverse:
                            array[aln.reference_end - 1 if aln.reference_end
                                  else aln.reference_start, 1] += 1
                        else:
                            array[aln.reference_start, 0] += 1

                    cover[GenomicInterval(chrom, 0, genomesize[chrom],
                                          '+'), i] = array[:, 0]
                    cover[GenomicInterval(chrom, 0, genomesize[chrom],
                                          '-'), i] = array[:, 1]

            return cover

        if cachedir:
            memmap_dir = os.path.join(cachedir, name)
        else:
            memmap_dir = None

        # At the moment, we treat the information contained
        # in each bw-file as unstranded
        cover = create_genomic_array(genomesize, stranded=True,
                                     storage=storage, memmap_dir=memmap_dir,
                                     conditions=samplenames,
                                     overwrite=overwrite,
                                     typecode=dtype,
                                     loader=bam_loader,
                                     loader_args=(bamfiles,))

        return cls(name, cover, gindexer, flank, stranded=True)

    @classmethod
    def create_from_bigwig(cls, name, bigwigfiles, regions, genomesize,
                           samplenames=None,
                           binsize=50, stepsize=50,
                           flank=4, storage='hdf5',
                           dtype='int',
                           overwrite=False,
                           cachedir=None):
        """Create a CoverageDataset class from a bigwig-file (or files).

        Parameters
        -----------
        name : str
            Name of the dataset
        bigwigfiles : str or list
            bigwig-file or list of bigwig files.
        gindxer : pandas.DataFrame or str
            bed-filename or content of a bed-file
            (in terms of a pandas.DataFrame).
        genomesize : dict
            Dictionary containing the genome size.
        samplenames : list
            List of samplenames. Default: None means that the filenames
            are used as samplenames as well.
        binsize : int
            binsize in basepairs. Default: 50.
        stepsize : int
            stepsize in basepairs. This defines the step size for traversing
            the genome. Default: 50.
        flank : int
            Adjacent flanking bins to use, where the bin size is determined
            by the binsize. Default: 4.
        storage : str
            Storage mode for storing the coverage data can be
            'step', 'ndarray', 'memmap' or 'hdf5'. Default: 'hdf5'.
        overwrite : boolean
            overwrite cachefiles. Default: False.
        cachedir : str or None
            Directory in which the cachefiles are located. Default: None.
        """

        gindexer = GenomicIndexer.create_from_file(regions, binsize,
                                                   stepsize)

        if isinstance(bigwigfiles, str):
            bigwigfiles = [bigwigfiles]

        if not samplenames:
            samplenames = bigwigfiles

        def bigwig_loader(cover, bigwigfiles, gindexer):
            print("load from bigwig")
            for i, sample_file in enumerate(bigwigfiles):
                bwfile = pyBigWig.open(sample_file)

                for j in range(len(gindexer)):
                    interval = gindexer[j]
                    cover[interval.start_as_pos, i] = \
                        np.sum(bwfile.values(interval.chrom,
                                             int(interval.start),
                                             int(interval.end)))
            return cover

        # At the moment, we treat the information contained
        # in each bw-file as unstranded
        if cachedir:
            memmap_dir = os.path.join(cachedir, name)
        else:
            memmap_dir = None

        cover = create_genomic_array(genomesize, stranded=False,
                                     storage=storage, memmap_dir=memmap_dir,
                                     conditions=samplenames,
                                     overwrite=overwrite,
                                     typecode=dtype,
                                     loader=bigwig_loader,
                                     loader_args=(bigwigfiles, gindexer))

        return cls(name, cover, gindexer, flank, stranded=False)

    def __repr__(self):  # pragma: no cover
        return "CoverageDataset('{}', ".format(self.name) \
               + "<BlgGenomicArray>, " \
               + "<GenomicIndexer>, " \
               + "flank={}, stranded={})".format(self.flank, self.stranded)

    def __getitem__(self, idxs):
        if isinstance(idxs, int):
            idxs = [idxs]
        if isinstance(idxs, slice):
            idxs = range(idxs.start if idxs.start else 0,
                         idxs.stop if idxs.stop else len(self),
                         idxs.step if idxs.step else 1)
        try:
            iter(idxs)
        except TypeError:
            raise IndexError('CoverageDataset.__getitem__: '
                             + 'index must be iterable')

        data = np.empty((len(idxs),) + self.shape[1:])

        for i, idx in enumerate(idxs):
            interval = self.gindexer[idx]

            pinterval = interval.copy()

            pinterval.start = interval.start - self.flank

            pinterval.end = interval.end + self.flank

            data[i] = np.asarray(self.covers[pinterval])

            if interval.strand == '-':
                # if the region is on the negative strand,
                # flip the order  of the coverage track
                data[i, :, :, :] = data[i, ::-1, ::-1, :]
        for transform in self.transformations:
            data = transform(data)

        return data

    def __len__(self):
        return len(self.gindexer)

    @property
    def shape(self):
        """Shape of the dataset"""
        return (len(self),
                2*self.flank + self.gindexer.binsize,
                2 if self.stranded else 1, len(self.covers.condition))

    @property
    def flank(self):
        """Flanking bins"""
        return self._flank

    @flank.setter
    def flank(self, value):
        if not isinstance(value, int) or value < 0:
            raise Exception('_flank must be a non-negative integer')
        self._flank = value