import json
import logging
import re
import urllib.request
from requests import Session, status_codes, RequestException
from requests.exceptions import RequestException

from pyats.connections import BaseConnection
from rest.connector.implementation import Implementation as RestImplementation
from rest.connector.utils import get_username_password

# create a logger for this module
logger = logging.getLogger(__name__)


class Implementation(RestImplementation):
    '''Rest Implementation for IOS-XE

    Implementation of Rest connection to IOS-XE devices supporting RESTCONF

    YAML Example
    ------------

        devices:
            eWLC:
                os: iosxe
                connections:
                    rest:
                        class: rest.connector.Rest
                        ip: 127.0.0.1
                        port: "443"
                        protocol: https
                        credentials:
                            rest:
                                username: admin
                                password: admin
                custom:
                    abstraction:
                        order: [os]

    Code Example
    ------------

        >>> from pyats.topology import loader
        >>> testbed = loader.load('topology.yaml')
        >>> device = testbed.devices['eWLC']
        >>> device.connect(alias='rest', via='rest')
        >>> device.rest.connected
        True
    '''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._is_connected = False
        if 'proxies' not in kwargs:
            self.proxies = urllib.request.getproxies()
    @property
    def connected(self):
        '''Is a device connected'''
        return self._is_connected

    def _get(self, restconf_path):

        '''GET REST Command to retrieve information from the device'''

        expected_status_codes = [
            status_codes.codes.ok,
            status_codes.codes.no_content
        ]

        
        url = f'{self._base_url}/{restconf_path}'
        logger.debug(f'GET: {url}')

        response = self._session.get(url=url, timeout=self._timeout)
        logger.debug(f'Response: {response.text}, '\
                f'headers: {response.headers}, '\
                f'reason: {response.reason}, '\
                f'status code: {response.status_code}')
        
        if response.status_code not in expected_status_codes:
            raise RequestException(f"Connection to {url} has returned the " \
                    f"following code {response.status_code}, instead of the " \
                    f"expected status code {status_codes.codes.ok}")

        return response


    @BaseConnection.locked
    def connect(self,
                timeout=30,
                content_type='json',
                verbose=False):
        '''connect to the device via REST

        Arguments
        ---------

            timeout (int): Timeout value
            content_type: Default for content type, json or xml
            proxies: Specify the proxy to use for connection as seen below.
                    {'http': 'http://proxy.esl.cisco.com:80/',
                    'ftp': 'http://proxy.esl.cisco.com:80/',
                    'https': 'http://proxy.esl.cisco.com:80/',
                    'no': '.cisco.com'}

        Raises
        ------

        Exception
        ---------

            If the connection did not go well

        Note
        ----

        Connecting via RESTCONF does not require contacting the device.
        This does nothing

        '''
        
        
        if self.connected:
            return

        logger.info(f'Establish RESTCONF connection to: {self.device.name}')

        self._timeout = timeout
        logger.debug(f'Timeout: {self._timeout}')

        # Set content-type
        logger.debug(f'Content type: {content_type}')

        # Set certificate validation, based on Device information
        verify = self.connection_info.get('verify', True)
        logger.debug(f'Certificate validation: {verify}')

        # Set protocol
        try:
            protocol = self.connection_info['protocol']
        except KeyError:
            protocol = "https"
        logger.debug(f'Protocol: {protocol}')

        # Set port
        try:
            port = self.connection_info['port']
        except KeyError:
            port = 443
        logger.debug(f'Port: {port}')

        # Set API endpoint. Prefer the host (FQDN) and fallback to IP (ip)
        try:
            endpoint = self.connection_info['host']
        except KeyError:
            endpoint = self.connection_info['ip'].exploded
        logger.debug(f'API endpoint: {endpoint}')

        # Set base URL
        try:
            base_url = self.connection_info['base_url']
        except KeyError:
            base_url = "/restconf/data"
        logger.debug(f'Base URL: {base_url}')

        # Set Endpoint
        try:
            endpoint = self.connection_info['host']
        except KeyError:
            endpoint = self.connection_info['ip'].exploded
        logger.debug(f'API endpoint: {endpoint}')

        # Set base URL
        self._base_url = f'{protocol}://{endpoint}:{port}{base_url}'
        logger.info(f'RESTCONF base URL: {self._base_url}')

        # Requests connection object
        self._session = Session()
        self._session.auth = get_username_password(self)
        self._session.verify = verify
        self._session.headers.update({'Accept': f'application/yang-data+{content_type}'})

        # support sshtunnel
        if 'sshtunnel' in self.connection_info:
            try:
                from unicon.sshutils import sshtunnel
            except ImportError:
                raise ImportError(
                    '`unicon` is not installed for `sshtunnel`. Please install by `pip install unicon`.'
                )
            try:
                tunnel_port = sshtunnel.auto_tunnel_add(self.device, self.via)
                if tunnel_port:
                    ip = self.device.connections[self.via].sshtunnel.tunnel_ip
                    port = tunnel_port
            except AttributeError as e:
                raise AttributeError(
                    "Cannot add ssh tunnel. Connection %s may not have ip/host or port.\n%s"
                    % (self.via, e))
 
        # ---------------------------------------------------------------------
        # Connect to "well-known" RESTCONF resource to "test", the
        # RESTCONF connection on 'connect'. Comparable to CLI (SSH) connection,
        # which triggers a "show version" on connect
        # ---------------------------------------------------------------------
        well_known_path = "Cisco-IOS-XE-native:native/version"

        # Connect to the device via requests
        content = self._get(well_known_path)

        self._is_connected = True
        logger.info(f"Successfully connected to: {endpoint}")

        return content


    @BaseConnection.locked
    def disconnect(self):
        """
            Does nothing, as there is no active persistent connection
        """
        self._is_connected = False
        return

    @BaseConnection.locked
    def get(self, restconf_path):

        '''GET REST Command to retrieve information from the device'''

        if not self.connected:
            raise Exception(f"{self.device.name} is not connected. "\
                    "Please connect the device first")

        return self._get(restconf_path=restconf_path)