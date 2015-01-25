from distutils.core import setup
import os


setup(
    name='mpworker',
    version='0.1',
    description='Easy to use stateful multiprocessing. Asyncio compatible.',
    url='https://github.com/dustyrockpyle/mpworker',
    download_url='https://github.com/dustyrockpyle/mpworker/tarball/v0.1',
    license='MIT',
    author='Dustin Pyle',
    author_email='dustyrockpyle@gmail.com',
    long_description=open(os.path.join(os.path.dirname(__file__), 'README.md')).read(),
    packages=['mpworker'],
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Intended Audience :: Developers',
        'Development Status :: 3 - Alpha',
    ],
)
