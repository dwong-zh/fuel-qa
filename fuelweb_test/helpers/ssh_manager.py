#    Copyright 2016 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os
import posixpath
import re
import traceback
from warnings import warn

from devops.helpers.metaclasses import SingletonMeta
from devops.helpers.ssh_client import SSHAuth
from devops.helpers.ssh_client import SSHClient
from paramiko import RSAKey
from paramiko import SSHException
import six

from fuelweb_test import logger
from fuelweb_test.settings import SSH_FUEL_CREDENTIALS
from fuelweb_test.settings import SSH_SLAVE_CREDENTIALS


class SSHManager(six.with_metaclass(SingletonMeta, object)):

    def __init__(self):
        logger.debug('SSH_MANAGER: Run constructor SSHManager')
        self.__connections = {}  # Disallow direct type change and deletion
        self.admin_ip = None
        self.admin_port = None
        self.admin_login = None
        self.__admin_password = None
        self.slave_login = None
        self.slave_fallback_login = 'root'
        self.__slave_password = None

    @property
    def connections(self):
        return self.__connections

    def initialize(self, admin_ip,
                   admin_login=SSH_FUEL_CREDENTIALS['login'],
                   admin_password=SSH_FUEL_CREDENTIALS['password'],
                   slave_login=SSH_SLAVE_CREDENTIALS['login'],
                   slave_password=SSH_SLAVE_CREDENTIALS['password']):
        """ It will be moved to __init__

        :param admin_ip: ip address of admin node
        :param admin_login: user name
        :param admin_password: password for user
        :param slave_login: user name
        :param slave_password: password for user
        :return: None
        """
        self.admin_ip = admin_ip
        self.admin_port = 22
        self.admin_login = admin_login
        self.__admin_password = admin_password
        self.slave_login = slave_login
        self.__slave_password = slave_password

    def _get_keys(self):
        keys = []
        admin_remote = self.get_remote(self.admin_ip)
        key_string = '/root/.ssh/id_rsa'
        with admin_remote.open(key_string) as f:
            keys.append(RSAKey.from_private_key(f))
        return keys

    def connect(self, remote):
        """ Check if connection is stable and return this one

        :param remote:
        :return:
        """
        try:
            from fuelweb_test.helpers.utils import RunLimit
            with RunLimit(
                    seconds=5,
                    error_message="Socket timeout! Forcing reconnection"):
                remote.check_call("cd ~")
        except Exception:
            logger.debug(traceback.format_exc())
            logger.debug('SSHManager: Check for current connection fails. '
                         'Trying to reconnect')
            remote = self.reconnect(remote)
        return remote

    def reconnect(self, remote):
        """ Reconnect to remote or update connection

        :param remote:
        :return:
        """
        ip = remote.hostname
        port = remote.port
        try:
            remote.reconnect()
        except SSHException:
            self.update_connection(ip=ip, port=port)
        return self.connections[(ip, port)]

    def init_remote(self, ip, port=22, custom_creds=None):
        """ Initialise connection to remote

        :param ip: IP of host
        :type ip: str
        :param port: port for SSH
        :type port: int
        :param custom_creds: custom creds
        :type custom_creds: dict
        """
        logger.debug('SSH_MANAGER: Create new connection for '
                     '{ip}:{port}'.format(ip=ip, port=port))

        keys = self._get_keys() if ip != self.admin_ip else []
        if ip == self.admin_ip:
            ssh_client = SSHClient(
                host=ip,
                port=port,
                auth=SSHAuth(
                    username=self.admin_login,
                    password=self.__admin_password,
                    keys=keys)
            )
            ssh_client.sudo_mode = SSH_FUEL_CREDENTIALS['sudo']
        elif custom_creds:
            ssh_client = SSHClient(
                host=ip,
                port=port,
                auth=SSHAuth(**custom_creds))
        else:
            try:
                ssh_client = SSHClient(
                    host=ip,
                    port=port,
                    auth=SSHAuth(
                        username=self.slave_login,
                        password=self.__slave_password,
                        keys=keys)
                )
            except SSHException:
                ssh_client = SSHClient(
                    host=ip,
                    port=port,
                    auth=SSHAuth(
                        username=self.slave_fallback_login,
                        password=self.__slave_password,
                        keys=keys)
                )
            ssh_client.sudo_mode = SSH_SLAVE_CREDENTIALS['sudo']

        self.connections[(ip, port)] = ssh_client
        logger.debug('SSH_MANAGER: New connection for '
                     '{ip}:{port} is created'.format(ip=ip, port=port))

    def get_remote(self, ip, port=22):
        """ Function returns remote SSH connection to node by ip address

        :param ip: IP of host
        :type ip: str
        :param port: port for SSH
        :type port: int
        :rtype: SSHClient
        """
        if (ip, port) in self.connections:
            logger.debug('SSH_MANAGER: Return existed connection for '
                         '{ip}:{port}'.format(ip=ip, port=port))
        else:
            self.init_remote(ip=ip, port=port)
        logger.debug('SSH_MANAGER: Connections {0}'.format(self.connections))
        return self.connect(self.connections[(ip, port)])

    def update_connection(self, ip, port=22, login=None, password=None,
                          keys=None):
        """Update existed connection

        :param ip: host ip string
        :param port: ssh port int
        :param login: login string
        :param password: password string
        :param keys: list of keys
        :return: None
        """
        if (ip, port) in self.connections:
            logger.debug('SSH_MANAGER: Close connection for {ip}:{port}'
                         .format(ip=ip, port=port))
            ssh_client = self.connections.pop((ip, port))
            ssh_client.close()
        if login and (password or keys):
            custom_creds = {
                'username': login,
                'password': password,
                'keys': keys
            }
        else:
            custom_creds = None
        self.init_remote(ip=ip, port=port, custom_creds=custom_creds)

    def clean_all_connections(self):
        for (ip, port), connection in self.connections.items():
            connection.clear()
            logger.debug('SSH_MANAGER: Close connection for {ip}:{port}'
                         .format(ip=ip, port=port))

    def execute(self, ip, cmd, port=22, sudo=None):
        remote = self.get_remote(ip=ip, port=port)
        with remote.sudo(enforce=sudo):
            return remote.execute(cmd)

    def check_call(
            self,
            ip,
            command, port=22, verbose=False, timeout=None,
            error_info=None,
            expected=None, raise_on_err=True,
            sudo=None
    ):
        """Execute command and check for return code

        :type ip: str
        :type command: str
        :type port: int
        :type verbose: bool
        :type timeout: int
        :type error_info: str
        :type expected: list
        :type raise_on_err: bool
        :type sudo: bool
        :rtype: ExecResult
        :raises: DevopsCalledProcessError
        """
        remote = self.get_remote(ip=ip, port=port)
        with remote.sudo(enforce=sudo):
            return remote.check_call(
                command=command,
                verbose=verbose,
                timeout=timeout,
                error_info=error_info,
                expected=expected,
                raise_on_err=raise_on_err
            )

    def execute_on_remote(self, ip, cmd, port=22, err_msg=None,
                          jsonify=False, assert_ec_equal=None,
                          raise_on_assert=True, yamlify=False, sudo=None):
        """Execute ``cmd`` on ``remote`` and return result.

        :param ip: ip of host
        :param port: ssh port
        :param cmd: command to execute on remote host
        :param err_msg: custom error message
        :param jsonify: bool, conflicts with yamlify
        :param assert_ec_equal: list of expected exit_code
        :param raise_on_assert: Boolean
        :param yamlify: bool, conflicts with jsonify
        :param sudo: use sudo: bool or None for default value set in settings
        :return: dict
        :raise: Exception
        """
        warn(
            'SSHManager().execute_on_remote is deprecated in favor of '
            'SSHManager().check_call.\n'
            'Please, do not use this method in any new tests. '
            'Old code will be updated later.', DeprecationWarning
        )
        if assert_ec_equal is None:
            assert_ec_equal = [0]

        if yamlify and jsonify:
            raise ValueError('Conflicting arguments: yamlify and jsonify!')

        orig_result = self.check_call(
            ip=ip,
            command=cmd,
            port=port,
            error_info=err_msg,
            expected=assert_ec_equal,
            raise_on_err=raise_on_assert,
            sudo=sudo
        )

        # Now create fallback result
        # TODO(astepanov): switch to SSHClient output after tests adoptation

        result = {
            'stdout': orig_result['stdout'],
            'stderr': orig_result['stderr'],
            'exit_code': orig_result['exit_code'],
            'stdout_str': ''.join(orig_result['stdout']).strip(),
            'stderr_str': ''.join(orig_result['stderr']).strip(),
        }

        if jsonify:
            result['stdout_json'] = orig_result.stdout_json
        elif yamlify:
            result['stdout_yaml'] = orig_result.stdout_yaml

        return result

    def execute_async_on_remote(self, ip, cmd, port=22, sudo=None):
        remote = self.get_remote(ip=ip, port=port)
        with remote.sudo(enforce=sudo):
            return remote.execute_async(cmd)

    def open_on_remote(self, ip, path, mode='r', port=22):
        remote = self.get_remote(ip=ip, port=port)
        return remote.open(path, mode)

    def upload_to_remote(self, ip, source, target, port=22, sudo=None):
        remote = self.get_remote(ip=ip, port=port)
        with remote.sudo(enforce=sudo):
            return remote.upload(source, target)

    def download_from_remote(self, ip, destination, target, port=22):
        remote = self.get_remote(ip=ip, port=port)
        return remote.download(destination, target)

    def exists_on_remote(self, ip, path, port=22):
        remote = self.get_remote(ip=ip, port=port)
        return remote.exists(path)

    def isdir_on_remote(self, ip, path, port=22):
        remote = self.get_remote(ip=ip, port=port)
        return remote.isdir(path)

    def isfile_on_remote(self, ip, path, port=22):
        remote = self.get_remote(ip=ip, port=port)
        return remote.isfile(path)

    def mkdir_on_remote(self, ip, path, port=22, sudo=None):
        remote = self.get_remote(ip=ip, port=port)
        with remote.sudo(enforce=sudo):
            return remote.mkdir(path)

    def rm_rf_on_remote(self, ip, path, port=22, sudo=None):
        remote = self.get_remote(ip=ip, port=port)
        with remote.sudo(enforce=sudo):
            return remote.rm_rf(path)

    def cond_upload(self, ip, source, target, port=22, condition='',
                    clean_target=False, sudo=None):
        """ Upload files only if condition in regexp matches filenames

        :param ip: host ip
        :param source: source path
        :param target: destination path
        :param port: ssh port
        :param condition: regexp condition
        :param clean_target: drop whole target contents by target recreate
        :param sudo: use sudo: bool or None for default value set in settings
        :return: count of files
        """

        # remote = self.get_remote(ip=ip, port=port)
        # maybe we should use SSHClient function. e.g. remote.isdir(target)
        # we can move this function to some *_actions class
        if self.isdir_on_remote(ip=ip, port=port, path=target):
            target = posixpath.join(target, os.path.basename(source))

        if clean_target:
            self.rm_rf_on_remote(ip=ip, port=port, path=target, sudo=sudo)
            self.mkdir_on_remote(ip=ip, port=port, path=target, sudo=sudo)

        source = os.path.expanduser(source)
        if not os.path.isdir(source):
            if re.match(condition, source):
                self.upload_to_remote(ip=ip, port=port,
                                      source=source, target=target, sudo=sudo)
                logger.debug("File '{0}' uploaded to the remote folder"
                             " '{1}'".format(source, target))
                return 1
            else:
                logger.debug("Pattern '{0}' doesn't match the file '{1}', "
                             "uploading skipped".format(condition, source))
                return 0

        files_count = 0
        for rootdir, _, files in os.walk(source):
            targetdir = os.path.normpath(
                os.path.join(
                    target,
                    os.path.relpath(rootdir, source))).replace("\\", "/")

            self.mkdir_on_remote(ip=ip, port=port, path=targetdir, sudo=sudo)

            for entry in files:
                local_path = os.path.join(rootdir, entry)
                remote_path = posixpath.join(targetdir, entry)
                if re.match(condition, local_path):
                    self.upload_to_remote(ip=ip,
                                          port=port,
                                          source=local_path,
                                          target=remote_path,
                                          sudo=sudo)
                    files_count += 1
                    logger.debug("File '{0}' uploaded to the "
                                 "remote folder '{1}'".format(source, target))
                else:
                    logger.debug("Pattern '{0}' doesn't match the file '{1}', "
                                 "uploading skipped".format(condition,
                                                            local_path))
        return files_count
