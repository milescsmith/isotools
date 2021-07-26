import typer
from pathlib import Path
from isotools import (
    DEFAULT_GENE_FILTER,
    DEFAULT_TRANSCRIPT_FILTER,
    DEFAULT_REF_TRANSCRIPT_FILTER
)
from isotools.transcriptome import Transcriptome


def main(
    pickled_ref: Path = typer.Argument(...),
    pickled_file: Path = typer.Argument(...)
) -> None:
    testing_xscript = Transcriptome.from_reference(pickled_ref)
    testing_xscript.load(pickled_file)

    gene_filter = DEFAULT_GENE_FILTER
    transcript_filter = DEFAULT_TRANSCRIPT_FILTER
    ref_filter = DEFAULT_REF_TRANSCRIPT_FILTER

    ref_filter['HIGH_SUPPORT'] = 'transcript_support_level=="1"'
    ref_filter['PROTEIN_CODING'] = 'transcript_type=="protein_coding"'
    testing_xscript.add_filter(gene_filter, transcript_filter, ref_filter)


if __name__ == "__main__":
    typer.run(main)
