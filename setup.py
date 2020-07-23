from setuptools import setup, find_packages
import os
import numpy.random
from glob import glob

os.system("export PY_IGNORE_IMPORTMISMATCH=1")
version = open('VERSION').read().strip()

setup(
    name="EUKulele",
    version=version,
    #distclass=distutils.command.bdist_conda.CondaDistribution,
    conda_buildnum=1,
    url="https://github.com/AlexanderLabWHOI/EUKulele",
    author="Arianna Krinos",
    author_email="akrinos@mit.edu",
    packages=['EUKulele','scripts'],
    package_dir={'EUKulele': 'src/EUKulele'},
    scripts=['bin/EUKulele','scripts/create_protein_table.py',\
             'scripts/mag_stats.py','scripts/names_to_reads.py','scripts/query_busco.py',\
             'scripts/configure_busco.sh','scripts/run_busco.sh','scripts/install_dependencies.sh'],
    license="MIT",
    include=['code'],
    setup_requires=['pytest-runner'],
    test_suite='tests',
    tests_require=['pytest'],
    install_requires=['setuptools','hypothesis',\
        'pandas','numpy','matplotlib','argparse','seaborn',\
        'multiprocess','chardet','biopython',\
        'joblib','ujson','pyyaml'],
    #packages=['EUKulele','EUKulele.tests','EUKulele.scripts'],
)