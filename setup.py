import setuptools

setuptools.setup(
    name = 'WS-API',
    packages = ['ws_api'],
    version = '0.28.0',
    license = 'GPL-3.0',
    description = 'Access your Wealthsimple account using their (GraphQL) API.',
    author = 'Guillaume Boudreau',
    author_email = 'guillaume@pommepause.com',
    url = 'https://github.com/gboudreau/ws-api-python',
    keywords = ['wealthsimple'],
    python_requires='>=3.10',
    install_requires = [
        'requests',
    ],
    classifiers = [
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Programming Language :: Python :: 3',
        "Programming Language :: Python :: 3.13"
    ],
)
