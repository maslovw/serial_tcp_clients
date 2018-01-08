from setuptools import setup

setup(
    name='serial_tcp_clients',
    version='2.0.1-dev',
    packages=['serialtcp'],
    install_requires=['pyserial>=3.3'],
    python_requires='~=3.5',
    url='https://github.com/maslovw/serial_tcp_clients',
    author='maslovw',
    author_email='serialtcp@maslovw.com',
    license='MIT',
    keywords='serial com port tcp server socket',
    description='share serial device through tcp connections'
)
