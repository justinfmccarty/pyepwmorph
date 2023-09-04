from distutils.core import setup
setup(
  name = 'pyepwmorph',         # How you named your package folder (MyLib)
  packages = ['pyepwmorph','pyepwmorph.models','pyepwmorph.morph','pyepwmorph.tools'],
  version = '0.2.3',      # Start with a small number and increase it with every change you make
  license='GPLv3',        # Chose a license from here: https://help.github.com/articles/licensing-a-repository
  description = 'A python package to enable simple and easy gathering of climate model data and morphing of EPW files',   # Give a short description about your library
  author = 'Justin McCarty',                   # Type in your name
  author_email = 'mccarty.justin.f@gmail.com',      # Type in your E-Mail
  url = 'https://github.com/justinfmccarty/pyepwmorph',   # Provide either the link to your github or to your website
  download_url = 'https://github.com/justinfmccarty/pyepwmorph/archive/refs/tags/v0.2.3.tar.gz',
  keywords = ['EPW', 'MORPH', 'TMY', 'CLIMATE CHANGE', 'CMIP6', 'PANGEO'],   # Keywords that define your package best
  install_requires=[            # what gets imported in files
          'timezonefinder',
          'xarray',
          'xclim',
          'dask',
          'pandas',
          'numpy',
          'gcsfs',
          'intake-esm',
          'pvlib',
          'meteocalc',
      ],
  classifiers=[
    'Development Status :: 5 - Production/Stable',      # Chose either "3 - Alpha", "4 - Beta" or "5 - Production/Stable" as the current state of your package
    'Intended Audience :: Science/Research',      # Define that your audience are developers
    'Topic :: Software Development :: Build Tools',
    'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',   # Again, pick a license
    'Programming Language :: Python :: 3.10',
  ],
)