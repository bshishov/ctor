from setuptools import setup, find_packages

with open('README.md', 'r') as f:
    long_description = f.read()

setup(
    name='ctor',
    version='0.1.1',
    description='Object tree serialization library for python',
    url='https://github.com/bshishov/ctor',
    author='Boris Shishov',
    author_email='borisshishov@gmail.com',
    long_description=long_description,
    long_description_content_type='text/markdown',
    package_dir={'': 'src'},
    packages=find_packages(where="src"),
    license='MIT',
    python_requires='>=3.7',
    extras_require={
        'dev': [
            'pytest',
            'pytest-cov',
            'coverage',
            'attrs'
        ]
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Operating System :: OS Independent',
        'Topic :: Software Development :: Libraries'
    ]
)
