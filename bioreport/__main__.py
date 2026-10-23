import sys


def main():
    # Keep internal worker startup on the existing package entrypoint, without
    # importing the CLI or opening a second Jupyter/display context.
    if sys.argv[1:] == ['--pdf-worker']:
        from .pdf_parallel import worker_main
        return worker_main()
    from .cli import main as cli_main
    return cli_main()

if __name__ == "__main__":
    main()
