__all__ = ('Writer', 'Reader', 'open')

import sys
import weakref
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

import numpy as np

if sys.platform == 'win32':
    from ._win32.multiresolutionimageinterface import (
        MultiResolutionImageReader as Reader,
        MultiResolutionImageWriter as Writer,
    )
else:
    from ctypes import cdll
    for path in Path(__file__).parent.rglob('lib*.so'):
        cdll.LoadLibrary(str(path))

    from ._linux.multiresolutionimageinterface import (
        MultiResolutionImageReader as Reader,
        MultiResolutionImageWriter as Writer,
    )


def format_slice(slices, limits):
	for s, limit in zip(slices, limits):
        yield slice(
            s.start or 0,
            s.stop or limit,
            s.step or 1,
        )


@dataclass
class Slide:
    path: str
    shape: Tuple[int]
    tile: int
    writer: object = field(default_factory=Writer, init=None)
    close: callable = field(init=False)

    def __post_init__(self):
        self.writer.openFile(self.path)
        self.close = weakref.finalize(self, self.writer.finishImage)

        self.writer.writeImageInformation(self.shape[1], self.shape[0])

    def __setitem__(self, slices: Tuple[slice], data: np.ndarray):
        ys, xs = format_slices(slices, self.shape)
        for (y, x), tile in zip(product(range(ys), range(xs)),
                                data.split(axis=[0, 1], tile=self.tile)):
            self.writer.writeBaseImagePartToLocation(x, y, tile.ravel())


@dataclass
class SlideView:
    slide: object

    @property
    def scales(self):
        return tuple(int(self.slide.getLevelDownsample(level))
                     for level in range(self.slide.getNumberOfLevels()))

    @property
    def shape(self) -> Tuple[int]:
        w, h = self.slide.getDimensions()
        return (h, w, 3)

    def __getitem__(self, slices: Tuple[slice]):
        ys, xs = format_slice(slices, self.shape)
        if ys.step not in self.scales or xs.step not in self.scales:
            raise ValueError(
                f'Both y-step and x-step should be in {self.scales}'
            )

        step = max(ys.step, xs.step)
        level = self.scales.index(step)
        return self.slide.getUCharPatch(
            xs.start,
            ys.start,
            (xs.stop - xs.start) // step,
            (ys.stop - ys.start) // step,
            level,
        )


@contextmanager
def open(filename: str):
    slide = Reader().open(filename)
    if slide is None:
        raise OSError(f'File not found or cannot be opened: {filename}')
    try:
        yield SlideView(slide)
    finally:
        slide.close()
