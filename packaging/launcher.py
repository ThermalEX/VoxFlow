"""Entry point of the packaged VoxFlow.exe."""

import multiprocessing

from voxflow.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()  # the speech worker process re-launches this executable
    raise SystemExit(main())
