import pickle
from pathlib import Path
from typing import Union

import pandas as pd
from intervaltree import IntervalTree  # , Interval

from .logger import isotools_logger as logger
from ._transcriptome_io import import_gff_transcripts, import_gtf_transcripts
from .gene import Gene

# as this class has diverse functionality, its split among:
# transcriptome.py (this file- initialization and user level basic functions)
# _transcriptome_io.py (input/output primary data files/tables)
# _transcriptome_stats.py (statistical methods)
# _trnascriptome_plots.py (plots)
# _transcriptome_filter.py (gene/transcript iteration and filtering)


class Transcriptome:
    """Contains sequencing data and annotation for Long Read Transcriptome Sequencing (LRTS) Experiments.

    :param pickle_file: Filename to restore previous data"""

    # initialization and save/restore data
    def __new__(cls, pickle_file=None, **kwargs):
        if pickle_file is not None:
            obj = cls.load(pickle_file)
        else:
            obj = super().__new__(cls)
        return obj

    def __init__(self, pickle_file=None, **kwargs):
        """Constructor method"""
        if "data" in kwargs:
            self.data, self.infos, self.chimeric = (
                kwargs["data"],
                kwargs.get("infos", dict()),
                kwargs.get("chimeric", {}),
            )
            assert "reference_file" in self.infos
            self.make_index()

    @classmethod
    def from_reference(
        cls, reference_file: Union[Path, str], file_format="auto", **kwargs
    ) -> "Transcriptome":
        """Creates a Transcriptome object by importing reference annotation.

        :param reference_file: Reference file in gff3 format or pickle file to restore previously imported annotation
        :type reference_file: str
        :param file_format: Specify the file format of the provided reference_file.
            If set to "auto" the file type is infrered from the extension."""
        tr = cls.__new__(cls)

        if isinstance(reference_file, str):
            reference_file = Path(reference_file)
        tr.infos = {"reference_file": reference_file}
        tr.chimeric = {}
        if file_format == "auto":
            file_format = reference_file.suffix
            if file_format == ".gz":
                file_format = Path(reference_file.stem).suffix
        logger.info(f"importing reference from {file_format} file {reference_file}")
        if file_format == ".gtf":
            tr.data = import_gtf_transcripts(reference_file, tr, **kwargs)
        elif file_format in (".gff", ".gff3"):
            tr.data = import_gff_transcripts(reference_file, tr, **kwargs)
        elif file_format == ".pkl":
            tr = pickle.load(open(reference_file, "rb"))
            if [k for k in tr.infos if k != "reference_file"]:
                logger.warning(
                    "the pickle file seems to contain additional expression information... extracting refrence"
                )
                tr = tr._extract_reference()
        else:
            logger.error(f"unknown file format {file_format}")
        return tr

    def save(self, pickle_file=None):
        """Saves transcriptome information (including reference) in a pickle file.

        :param pickle_file: Filename to save data"""
        if pickle_file is None:
            pickle_file = (
                self.infos["out_file_name"] + ".isotools.pkl"
            )  # key error if not set
        logger.info(f"saving transcriptome to {pickle_file}")
        pickle.dump(self, open(pickle_file, "wb"))

    @classmethod
    def load(cls, pickle_file) -> "Transcriptome":
        """Restores transcriptome information from a pickle file.

        :param pickle_file: Filename to restore data"""

        logger.info(f"loading transcriptome from {pickle_file}")
        return pickle.load(open(pickle_file, "rb"))

    def save_reference(self, pickle_file=None):
        """Saves the reference information of a transcriptome in a pickle file.

        :param pickle_file: Filename to save data"""
        if pickle_file is None:
            pickle_file = self.infos["reference_file"] + ".isotools.pkl"
        logger.info("saving reference to " + pickle_file)
        ref_tr = self._extract_reference()
        pickle.dump(ref_tr, open(pickle_file, "wb"))

    def _extract_reference(self):
        if not [k for k in self.infos if k != "reference_file"]:
            return self  # only reference info - assume that self.data only contains reference data
        # make a new transcriptome
        ref_tr = type(self)(
            data={}, infos={"reference_file": self.infos["reference_file"]}
        )
        # extract the reference genes and link them to the new ref_tr
        for chrom, tree in self.data.items():
            ref_tr.data[chrom] = IntervalTree(
                Gene(
                    g.start,
                    g.end,
                    {k: g.data[k] for k in Gene.required_infos + ["reference"]},
                    ref_tr,
                )
                for g in tree
                if g.is_annotated
            )
        return ref_tr

    def make_index(self):
        """Updates the index of gene names and ids (e.g. used by the the [] operator)."""
        idx = dict()
        for g in self:
            if g.id in idx:  # at least id should be unique - maybe raise exception?
                logger.warn(
                    f"{g.id} seems to be ambigous: {str(self[g.id])} vs {str(g)}"
                )
            idx[g.name] = g
            idx[g.id] = g
        self._idx = idx

    ##### basic user level functionality
    def __getitem__(self, key):
        """
        Syntax: self[key]

        :param key: May either be the gene name or the gene id
        :return: The gene specified by key.
        """
        return self._idx[key]

    def __len__(self):
        """Syntax: len(self)

        :return: The number of genes."""
        return self.n_genes

    def __contains__(self, key):
        """Syntax: key in self

        Checks whether key is in self.

        :param key: May either be the gene name or the gene id"""
        return key in self._idx

    def remove_chromosome(self, chromosome):
        """Deletes the chromosome from the transcriptome

        :param chromosome: Name of the chromosome to remove"""
        del self.data[chromosome]
        self.make_index()

    def _get_sample_idx(self, group_column="name"):
        "a dict with group names as keys and index lists as values"
        return self.infos["sample_table"].groupby(group_column).groups

    @property
    def sample_table(self):
        """The sample table contains sample names, group information, long read coverage, as well as all other potentially relevant information on the samples."""
        try:
            return self.infos["sample_table"]
        except KeyError:
            return pd.DataFrame(
                columns=["name", "file", "group", "nonchimeric_reads", "chimeric_reads"]
            )

    @property
    def samples(self) -> list:
        """An ordered list of sample names."""
        return list(self.sample_table.name)

    def groups(self, by="group") -> dict:
        """Get sample groups as defined in columns of the sample table.

        :param by: A column name of the sample table that defines the grouping.
        :return: Dict with groupnames as keys and list of sample names as values.
        """
        return dict(self.sample_table.groupby(by)["name"].apply(list))

    @property
    def n_transcripts(self) -> int:
        """The total number of transcripts isoforms."""
        if self.data is None:
            return 0
        return sum(g.n_transcripts for g in self)

    @property
    def n_genes(self) -> int:
        """The total number of genes."""
        if self.data is None:
            return 0
        return sum((len(t) for t in self.data.values()))

    @property
    def novel_genes(self) -> int:  # this is used for id assignment
        """The total number of novel (not reference) genes."""
        try:
            return self.infos["novel_counter"]
        except KeyError:
            self.infos["novel_counter"] = 0
            return 0

    @property
    def chromosomes(self) -> list:
        """The list of chromosome names."""
        return list(self.data)

    def __str__(self):
        return "{} object with {} genes and {} transcripts".format(
            type(self).__name__, self.n_genes, self.n_transcripts
        )

    def __repr__(self):
        return object.__repr__(self)

    def __iter__(self):
        return (gene for tree in self.data.values() for gene in tree)

    ### IO: load new data from primary data files
    ### filtering functionality and iterators
    from ._transcriptome_filter import (
        add_filter,
        add_qc_metrics,
        iter_genes,
        iter_ref_transcripts,
        iter_transcripts,
    )

    ### IO: output data as tables or other human readable format
    ### IO: utility functions
    from ._transcriptome_io import (
        _add_chimeric,
        _add_novel_genes,
        _add_sample_transcript,
        _get_intersects,
        add_sample_from_bam,
        add_short_read_coverage,
        chimeric_table,
        collapse_immune_genes,
        export_alternative_splicing,
        gene_table,
        remove_samples,
        remove_short_read_coverage,
        transcript_table,
        write_gtf,
    )

    # statistic: summary tables (can be used as input to plot_bar / plot_dist)
    ### statistic: differential splicing, alternative_splicing_events
    from ._transcriptome_stats import (
        alternative_splicing_events,
        altsplice_stats,
        altsplice_test,
        direct_repeat_hist,
        downstream_a_hist,
        exons_per_transcript_hist,
        filter_stats,
        splice_dependence_test,
        transcript_coverage_hist,
        transcript_length_hist,
        transcripts_per_gene_hist,
    )
