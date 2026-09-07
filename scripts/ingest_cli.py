import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.ingest import ingest_repository


def main():
    parser = argparse.ArgumentParser(description="Ingest a local repo into the RepoMind vector store.")
    parser.add_argument("--repo", required=True, help="Path to the repository/folder to index")
    parser.add_argument("--ext", nargs="*", default=None, help="File extensions to include, e.g. .py .md")
    args = parser.parse_args()

    print(f"Ingesting {args.repo} ...")
    store, stats = ingest_repository(args.repo, args.ext)

    data_dir = Path(settings.data_dir)
    store.save(data_dir)

    print(f"Files scanned:   {stats['files_scanned']}")
    print(f"Files ingested:  {stats['files_ingested']}")
    print(f"Chunks created:  {stats['chunks_created']}")
    if stats["skipped_files"]:
        print(f"Skipped ({len(stats['skipped_files'])}): {stats['skipped_files'][:5]}...")
    print(f"Index saved to:  {data_dir.resolve()}")


if __name__ == "__main__":
    main()
