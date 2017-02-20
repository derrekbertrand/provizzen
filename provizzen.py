#!/usr/bin/env python
import json
import os
import sys
import subprocess

class Provizzen(object):
    '''A class designed to provision a server using shell commands.
    '''

    def __init__( self, defaults ):
        self.defaults = defaults
        self.config = None

        return


    def setConfigFromFile( self, path=None ):
        # open path or config.json from provizzen's directory
        if path == None:
            path = os.path.dirname(os.path.realpath(__file__))+'/config.json'

        # load config
        with open(path) as config_file:
            self.setConfigFromJson(json.load(config_file))

        return

    def setConfigFromJson( self, json ):
        self.config = Provizzen.mergeConfig(self.defaults, json)

        # todo: validate user data structure

        return

    def bootstrap( self ):
        if self.config == None:
            raise Exception('You must load a config before bootstrapping your system!')

        self.call('echo', '\n=== START ===\n')

        self.initEpel()
        self.initFirewall()
        self.initSkel()
        self.initSshd()
        # updates()
        self.initUsers()
        self.initMotd()
        if self.config['mariadb']['install']:
            self.initMariaDB()
        if self.config['nginx']['install']:
            self.initNginx()
        if self.config['php']['install']:
            self.initPHP()

        self.call('echo', '\n=== END ===\n')

        return

    def initEpel( self ):
        print 'Bootstrapping EPEL...'

        self.call(['yum', 'install', '-y', 'epel-release'])

        print 'OK'
        return

    def initFirewall( self ):
        print 'Bootstrapping firewalld...'

        self.call(['yum', 'install', '-y', 'firewalld'])
        self.call(['systemctl', 'start', 'firewalld'])
        self.call(['systemctl', 'enable', 'firewalld'])


        self.call(['firewall-cmd', '--permanent', '--remove-service=dhcpv6-client'])
        self.call(['firewall-cmd', '--permanent', '--remove-service=ssh'])

        # add the port from sshd config
        self.call(['firewall-cmd', '--permanent', '--add-port='+self.config['sshd']['port']+'/tcp'])

        self.call(['firewall-cmd', '--reload'])

        print 'OK'
        return

    def initMariaDB( self ):
        print 'Bootstrapping MariaDB...'

        self.call(['yum', '-y', 'install', 'mariadb-server', 'mariadb'])

        self.call(['systemctl', 'start', 'mariadb'])
        self.call(['systemctl', 'enable', 'mariadb'])

        for account in self.config['mariadb']['accounts']:
            sql = 'CREATE DATABASE IF NOT EXISTS '+account['database']+';\n'
            sql += "CREATE USER '"+account['username']+"'@'localhost' IDENTIFIED BY '"+account['password']+"';\n"
            sql += "GRANT ALL PRIVILEGES ON "+account['database']+".* TO '"+account['username']+"'@'localhost';\n"
            sql += "FLUSH PRIVILEGES;"

            self.call(['mysql', '-uroot', '-e', sql])


        print '- Be sure to run `mysql_secure_installation`'
        print 'OK'
        return

    def initMotd( self ):
        if ('motd' in self.config) and (type(self.config['motd']) == str):
            print 'Bootstrapping MOTD...'

            motd_file = open('/etc/motd', 'w')
            motd_file.write(self.config['motd'])
            motd_file.close()

            print 'OK'
        else:
            print 'Skipping MOTD.'

        return

    def initNginx( self ):
        print 'Bootstrapping nginx...'

        self.call(['yum', '-y', 'install', 'nginx'])

        # open firewall ports for the service
        self.call(['firewall-cmd', '--permanent', '--add-service=http'])
        self.call(['firewall-cmd', '--permanent', '--add-service=https'])
        self.call(['firewall-cmd', '--reload'])

        self.call(['systemctl', 'start', 'nginx'])
        self.call(['systemctl', 'enable', 'nginx'])

        print 'OK'
        return

    def initPHP( self )::
        print 'Bootstrapping PHP...'

        self.call(['wget', '-qO', '/root/setup-ius.sh', 'https://setup.ius.io/'])
        self.call(['bash', '/root/setup-ius.sh'])

        if self.config['php']['version'] == '7.0':
            self.call(['yum', 'install', '-y', 'php70u-fpm-nginx', 'php70u-cli', 'php70u-mysqlnd'])
        elif self.config['php']['version'] == '7.1':
            self.call(['yum', 'install', '-y', 'php71u-fpm-nginx', 'php71u-cli', 'php71u-mysqlnd'])
        else:
            raise Exception('Invalid PHP version: '+self.config['php']['version'])

        print 'OK'
        return

    # this makes sure we have the files necessary for SSH
    def initSkel( self ):
        print 'Bootstrapping skel...'

        for skel in self.config['skel']:
            if skel['type'] == 'dir':
                skel = Provizzen.mergeConfig({'type': 'dir', 'mode': '755', 'path': 'your_admin_botched_skel'}, skel)
                self.call(['mkdir', '-p', '/etc/skel/'+skel['path']])
                self.call(['chmod', skel['mode'], '/etc/skel/'+skel['path']])
            elif skel['type'] == 'file':
                skel = Provizzen.mergeConfig({'type': 'file', 'mode': '644', 'path': 'your_admin_botched_skel'}, skel)
                self.call(['touch', '/etc/skel/'+skel['path']])
                self.call(['chmod', skel['mode'], '/etc/skel/'+skel['path']])
            else:
                raise Exception('Skel type must be "dir" or "file"; "%s" given' % str(skel['type']))

        print 'OK'
        return

    def initSshd( self ):
        print 'Bootstrapping SSH policy...'

        self.sedIE('^(#?)PasswordAuthentication .+$', 'PasswordAuthentication no', '/etc/ssh/sshd_config')
        self.sedIE('^(#?)ChallengeResponseAuthentication .+$', 'ChallengeResponseAuthentication no', '/etc/ssh/sshd_config')
        self.sedIE('^(#?)Port .+$', 'Port '+self.config['sshd']['port'], '/etc/ssh/sshd_config')
        # if we are setting up users, then don't allow root access
        if self.config['sshd']['disable_root']:
            self.sedIE('^(#?)PermitRootLogin .+$', 'PermitRootLogin no', '/etc/ssh/sshd_config')
        else:
            print '- Allowing remote access as root, like a moron'

        self.call(['systemctl', 'restart', 'sshd.service'])

        print 'OK'
        return

    def initUpdates( self ):
        print 'Bootstrapping updates...'

        # do an update now
        self.call(['yum', 'update', '-y'])

        # install yum-cron to automatically update the server
        self.call(['yum', 'install', '-y', 'yum-cron'])
        self.sedI('update_cmd', 'update_cmd = security', '/etc/yum/yum-cron.conf')

        # sed -i '/update_cmd/c\update_cmd = security' /etc/yum/yum-cron.conf
        # sed -i '/apply_updates/c\apply_updates = yes' /etc/yum/yum-cron.conf
        # systemctl start yum-cron
        # systemctl enable yum-cron

        print 'OK'
        return

    def initUsers( self ):
        print 'Bootstrapping user accounts...'

        for user in self.config['users']:
            self.initUser(user)

        if self.config['sshd']['disable_root']:
            self.call(['passwd', '-l', 'root'])

        # note that we don't lock root if we don't have a users config group
        print 'OK'
        return

    def initUser( self, user ):
        # create user
        self.call(['adduser', user['name']])


        if len(user['pass']):
            p = self.procOpenPipe(['passwd', user['name'], '--stdin'])
            p.communicate(input=user['pass'])

        # add user to whatever groups
        for group in user['groups']:
            self.call(['usermod', '-a', '-G', group, user['name']])

        # add the user's keys
        if len(user['authorized_keys']):
            keyfile = open('/home/'+user['name']+'/.ssh/authorized_keys', 'w')

            for key in user['authorized_keys']:
                keyfile.write(key+'\n')

            keyfile.close()

        return

    def call( self, call_args ):
        with open(self.config['logfile'], 'a') as logfile:
            ret = subprocess.call(call_args, stdout=logfile, stderr=subprocess.STDOUT)

        return ret

    def procOpenPipe( self, call_args ):
        return subprocess.Popen(call_args,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

    def sedI( self, search, replace, filename ):
        return self.call([
            'sed',
            '-i',
            "/"+search+"/c\\"+replace,
            filename
        ])

    def sedIE( self, regex, replace, filename ):
        return self.call([
            'sed',
            '-i',
            '-E',
            's/'+regex+'/'+replace+'/',
            filename
        ])

    @staticmethod
    def mergeConfig( dest, src, path=[] ):
        # if they are both dictionaries, we recursively merge it
        if isinstance(dest, dict) and isinstance(src, dict):
            tmp_dict = dest
            for key in src:
                # key conflict, merge
                if key in dest:
                    dest[key] = Provizzen.mergeConfig(dest[key], src[key], path+[str(key)])
                # no conflict, just add the key
                else:
                    dest[key] = src[key]
                #endif
            #endfor
            return dest
        # it is a list, so append
        elif isinstance(dest, list) and isinstance(src, list):
            return dest + src
        # there might be a type conflict
        elif isinstance(dest, list) or isinstance(dest, dict):
            raise Exception('Config type conflict at %s; expected type %s, found type %s' % ('.'.join(path), type(dest), type(src)))
        # for any other type, src just takes precedence
        else:
            return src

if __name__ == '__main__':
    # merge config file with defaults
    prov = Provizzen({
        'users': [],
        'logfile': '/root/provizzen_log',
        'sshd': {'port': '12222', 'disable_root': True},
        'mariadb': {
            'install': True,
            'accounts': []
        },
        'nginx': {
            'install': True
        },
        'php': {
            'install': True,
            'version': '7.1'
        },
        'skel': [
            {'type': 'dir', 'mode': '700', 'path': '.ssh'},
            {'type': 'file', 'mode': '600', 'path': '.ssh/authorized_keys'}
        ]})
    prov.setConfigFromFile()
    prov.bootstrap()

