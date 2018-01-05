from distutils.core import setup

setup(
    name='serial_tcp_clients',
    version='2.00',
    packages=['serialtcp'],
    install_requires=['pyserial>=3.3'],
    url='',
    license='',
    author='maslovw',
    author_email='serialtcp@maslovw.com',
    description='share serial device through tcp connections'
)
