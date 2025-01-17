from doctest import ELLIPSIS

import numpy as np
import pytest
import torch
from matplotlib import pyplot as plt
from sybil import Sybil
from sybil.parsers.doctest import DocTestParser
from sybil.parsers.markdown import PythonCodeBlockParser

import dynamiqs


def sybil_setup(namespace):
    namespace['dq'] = dynamiqs
    namespace['np'] = np
    namespace['plt'] = plt
    namespace['torch'] = torch


# doctest fixture
@pytest.fixture(scope='session', autouse=True)
def torch_set_printoptions():
    torch.set_printoptions(precision=3, sci_mode=False)


# doctest fixture
@pytest.fixture(scope='session', autouse=True)
def mplstyle():
    dynamiqs.plots.utils.mplstyle()


# doctest fixture
@pytest.fixture()
def renderfig():
    def savefig_code(figname):
        filename = f'docs/figs-code/{figname}.png'
        plt.gcf().savefig(filename, bbox_inches='tight', dpi=300)

    return savefig_code


# sybil configuration
pytest_collect_file = Sybil(
    parsers=[DocTestParser(optionflags=ELLIPSIS), PythonCodeBlockParser()],
    patterns=['*.py'],
    setup=sybil_setup,
    fixtures=['renderfig'],
).pytest()
