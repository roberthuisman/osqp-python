import os
import shutil as sh
import sys
from glob import glob
from platform import system
from shutil import copyfile, copy
from subprocess import call, check_output, check_call, CalledProcessError, STDOUT

from setuptools import setup, find_namespace_packages, Extension
from setuptools.command.build_ext import build_ext
import distutils.sysconfig as sysconfig

import argparse

OSQP_ARG_MARK = '--osqp'

parser = argparse.ArgumentParser(description='OSQP Setup script arguments.')
parser.add_argument(
    OSQP_ARG_MARK,
    dest='osqp',
    action='store_true',
    default=False,
    help='Put this first to ensure following arguments are parsed correctly')
parser.add_argument(
    '--long',
    dest='long',
    action='store_true',
    default=False,
    help='Use long integers')
parser.add_argument(
    '--debug',
    dest='debug',
    action='store_true',
    default=False,
    help='Compile extension in debug mode')
args, unknown = parser.parse_known_args()

# necessary to remove OSQP args before passing to setup:
if OSQP_ARG_MARK in sys.argv:
    sys.argv = sys.argv[0:sys.argv.index(OSQP_ARG_MARK)]

# Add parameters to cmake_args and define_macros
cmake_args = ["-DUNITTESTS=OFF"]
cmake_build_flags = []
define_macros = []
lib_subdir = []

# Check if windows linux or mac to pass flag
if system() == 'Windows':
    cmake_args += ['-G', 'Visual Studio 14 2015']
    # Differentiate between 32-bit and 64-bit
    if sys.maxsize // 2 ** 32 > 0:
        cmake_args[-1] += ' Win64'
    cmake_build_flags += ['--config', 'Release']
    lib_name = 'osqp.lib'
    lib_subdir = ['Release']

else:  # Linux or Mac
    cmake_args += ['-G', 'Unix Makefiles']
    lib_name = 'libosqp.a'

# Pass Python option to CMake and Python interface compilation
cmake_args += ['-DPYTHON=ON']

# Remove long integers for numpy compatibility (default args.long == False)
# https://github.com/numpy/numpy/issues/5906
# https://github.com/ContinuumIO/anaconda-issues/issues/3823
if not args.long:
    print("Disabling LONG\n" +
          "Remove long integers for numpy compatibility. See:\n" +
          " - https://github.com/numpy/numpy/issues/5906\n" +
          " - https://github.com/ContinuumIO/anaconda-issues/issues/3823\n" +
          "You can reenable long integers by passing: "
          "--osqp --long argument.\n")
    cmake_args += ['-DDLONG=OFF']

# Pass python to compiler launched from setup.py
define_macros += [('PYTHON', None)]

# Pass python include dirs to cmake
cmake_args += ['-DPYTHON_INCLUDE_DIRS=%s' % sysconfig.get_python_inc()]


# Define osqp and qdldl directories
current_dir = os.getcwd()
osqp_dir = os.path.join('osqp_sources')
osqp_ext_src_dir = os.path.join('src', 'extension', 'src')
osqp_build_dir = os.path.join(osqp_dir, 'build')
qdldl_dir = os.path.join(osqp_dir, 'lin_sys', 'direct', 'qdldl')

osqp2_dir = os.path.join('osqp2_sources')
osqp2_ext_src_dir = os.path.join('src', 'extension2', 'src')
osqp2_build_dir = os.path.join(osqp2_dir, 'build')
qdldl2_dir = os.path.join(osqp2_dir, 'lin_sys', 'direct', 'qdldl')


# Interface files
class get_numpy_include(object):
    """Returns Numpy's include path with lazy import.
    """
    def __str__(self):
        import numpy
        return numpy.get_include()


# Set optimizer flag
if system() != 'Windows':
    compile_args = ["-O3"]
else:
    compile_args = []

# If in debug mode
if args.debug:
    print("Debug mode")
    compile_args += ["-g"]
    cmake_args += ["-DCMAKE_BUILD_TYPE=Debug"]

# External libraries
library_dirs = []
libraries = []
if system() == 'Linux':
    libraries += ['rt']
if system() == 'Windows':
    # They moved the stdio library to another place.
    # We need to include this to fix the dependency
    libraries += ['legacy_stdio_definitions']


def prepare_codegen(osqp_dir, qdldl_dir):
    osqp_codegen_sources_dir = os.path.join('src', 'osqp', 'codegen', 'sources')
    if os.path.exists(osqp_codegen_sources_dir):
        sh.rmtree(osqp_codegen_sources_dir)
    os.makedirs(osqp_codegen_sources_dir)

    # OSQP C files
    cfiles = [os.path.join(osqp_dir, 'src', f)
              for f in os.listdir(os.path.join(osqp_dir, 'src'))
              if f.endswith('.c') and f not in ('cs.c', 'ctrlc.c', 'polish.c',
                                                'lin_sys.c')]
    cfiles += [os.path.join(qdldl_dir, f)
               for f in os.listdir(qdldl_dir)
               if f.endswith('.c')]
    cfiles += [os.path.join(qdldl_dir, 'qdldl_sources', 'src', f)
               for f in os.listdir(os.path.join(qdldl_dir, 'qdldl_sources',
                                                'src'))]
    osqp_codegen_sources_c_dir = os.path.join(osqp_codegen_sources_dir, 'src')
    if os.path.exists(osqp_codegen_sources_c_dir):  # Create destination directory
        sh.rmtree(osqp_codegen_sources_c_dir)
    os.makedirs(osqp_codegen_sources_c_dir)
    for f in cfiles:  # Copy C files
        copy(f, osqp_codegen_sources_c_dir)

    # List with OSQP H files
    hfiles = [os.path.join(osqp_dir, 'include', f)
              for f in os.listdir(os.path.join(osqp_dir, 'include'))
              if f.endswith('.h') and f not in ('qdldl_types.h',
                                                'osqp_configure.h',
                                                'cs.h', 'ctrlc.h', 'polish.h',
                                                'lin_sys.h')]
    hfiles += [os.path.join(qdldl_dir, f)
               for f in os.listdir(qdldl_dir)
               if f.endswith('.h')]
    hfiles += [os.path.join(qdldl_dir, 'qdldl_sources', 'include', f)
               for f in os.listdir(os.path.join(qdldl_dir, 'qdldl_sources',
                                                'include'))
               if f.endswith('.h')]
    osqp_codegen_sources_h_dir = os.path.join(osqp_codegen_sources_dir, 'include')
    if os.path.exists(osqp_codegen_sources_h_dir):  # Create destination directory
        sh.rmtree(osqp_codegen_sources_h_dir)
    os.makedirs(osqp_codegen_sources_h_dir)
    for f in hfiles:  # Copy header files
        copy(f, osqp_codegen_sources_h_dir)

    # List with OSQP configure files
    configure_files = [os.path.join(osqp_dir, 'configure', 'osqp_configure.h.in'),
                       os.path.join(qdldl_dir, 'qdldl_sources', 'configure',
                                    'qdldl_types.h.in')]
    osqp_codegen_sources_configure_dir = os.path.join(osqp_codegen_sources_dir,
                                                      'configure')
    if os.path.exists(osqp_codegen_sources_configure_dir):
        sh.rmtree(osqp_codegen_sources_configure_dir)
    os.makedirs(osqp_codegen_sources_configure_dir)
    for f in configure_files:  # Copy configure files
        copy(f, osqp_codegen_sources_configure_dir)

    # Copy cmake files
    copy(os.path.join(osqp_dir, 'src',     'CMakeLists.txt'),
         osqp_codegen_sources_c_dir)
    copy(os.path.join(osqp_dir, 'include', 'CMakeLists.txt'),
         osqp_codegen_sources_h_dir)


_osqp = Extension('osqp._osqp',
                  define_macros=define_macros,
                  libraries=libraries,
                  library_dirs=library_dirs,
                  include_dirs=[
                        os.path.join(osqp_dir, 'include'),      # osqp.h
                        os.path.join(qdldl_dir),                # qdldl_interface header to extract workspace for codegen
                        os.path.join(qdldl_dir, "qdldl_sources", "include"),     # qdldl includes for file types
                        os.path.join('src', 'extension', 'include'),   # auxiliary .h files
                        get_numpy_include()
                  ],
                  extra_objects=[os.path.join('src', 'extension', 'src', lib_name)],
                  sources=glob(os.path.join('src', 'extension', 'src', '*.c')),
                  extra_compile_args=compile_args)


spam = Extension('osqp.spam',
                  define_macros=define_macros,
                  libraries=libraries,
                  library_dirs=library_dirs,
                  include_dirs=[
                        os.path.join(osqp2_dir, 'include'),      # osqp.h
                        os.path.join(qdldl2_dir),                # qdldl_interface header to extract workspace for codegen
                        os.path.join(qdldl2_dir, "qdldl_sources", "include"),     # qdldl includes for file types
                        os.path.join('src', 'extension2', 'include'),   # auxiliary .h files
                        get_numpy_include()
                  ],
                  extra_objects=[os.path.join('src', 'extension2', 'src', lib_name)],
                  sources=glob(os.path.join('src', 'extension2', 'src', '*.c')),
                  extra_compile_args=compile_args)


# prepare_codegen(osqp2_dir, qdldl2_dir)
prepare_codegen(osqp_dir, qdldl_dir)    # Perform at the end since extension2 is broken wrt codegen


class CMakeExtension(Extension):
    def __init__(self, name, sourcedir=''):
        Extension.__init__(self, name, sources=[])
        self.sourcedir = os.path.abspath(sourcedir)


class CMakeBuild(build_ext):
    def build_extension(self, ext):
        if ext.name == 'osqp._osqp':
            self.build_extension_legacy(ext, osqp_ext_src_dir, osqp_build_dir)
        elif ext.name == 'osqp.spam':
            self.build_extension_legacy(ext, osqp2_ext_src_dir, osqp2_build_dir)
        else:
            self.build_extension_pybind11(ext)
        super().build_extension(ext)

    def build_extension_legacy(self, ext, src_dir, build_dir):
        # Compile OSQP using CMake

        # Create build directory
        if os.path.exists(build_dir):
            sh.rmtree(build_dir)
        os.makedirs(build_dir)
        os.chdir(build_dir)

        try:
            check_output(['cmake', '--version'])
        except OSError:
            raise RuntimeError("CMake must be installed to build OSQP")

        # Compile static library with CMake
        call(['cmake'] + cmake_args + ['..'])
        call(['cmake', '--build', '.', '--target', 'osqpstatic', '-DBUILD_TESTING=OFF'] +
             cmake_build_flags)

        # Change directory back to the python interface
        os.chdir(current_dir)

        # Copy static library to src folder
        lib_origin = [build_dir, 'out'] + lib_subdir + [lib_name]
        lib_origin = os.path.join(*lib_origin)
        copyfile(lib_origin, os.path.join(src_dir, lib_name))

    def build_extension_pybind11(self, ext):
        extdir = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))
        cmake_args = ['-DCMAKE_LIBRARY_OUTPUT_DIRECTORY=' + extdir,
                      '-DPYTHON_EXECUTABLE=' + sys.executable]

        cfg = 'Debug' if self.debug else 'Release'
        build_args = ['--config', cfg]

        if system() == "Windows":
            cmake_args += ['-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_{}={}'.format(cfg.upper(), extdir)]
            if sys.maxsize > 2**32:
                cmake_args += ['-A', 'x64']
            build_args += ['--', '/m']
        else:
            cmake_args += ['-DCMAKE_BUILD_TYPE=' + cfg]
            build_args += ['--', '-j2']

        if not os.path.exists(self.build_temp):
            os.makedirs(self.build_temp)

        check_call(['cmake', ext.sourcedir] + cmake_args, cwd=self.build_temp)
        check_call(['cmake', '--build', '.'] + build_args, cwd=self.build_temp)


# Read README.rst file
def readme():
    with open('README.rst') as f:
        return f.read()


with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setup(name='osqp',
      author='Bartolomeo Stellato, Goran Banjac',
      author_email='bartolomeo.stellato@gmail.com',
      description='OSQP: The Operator Splitting QP Solver',
      long_description=readme(),
      package_dir={'': 'src'},
      include_package_data=True,  # Include package data from MANIFEST.in
      install_requires=requirements,
      license='Apache 2.0',
      url="https://osqp.org/",
      cmdclass={'build_ext': CMakeBuild},
      packages=find_namespace_packages(where='src'),
      ext_modules=[_osqp, spam, CMakeExtension('osqp.ext')])
