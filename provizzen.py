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
        self.pwd = os.path.dirname(os.path.realpath(__file__))

        return

    def bootstrap( self ):
        if self.config == None:
            raise Exception('You must load a config before bootstrapping your system!')

        self.call(['echo', '\n=== START ===\n'])

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
        self.initDev()
        if self.config['nginx']['install'] and self.config['php']['install']:
            self.initFpm()

        self.call(['echo', '\n=== END ===\n'])

        return

    def initDev( self ):
        print 'Boostrapping development tools...'

        self.call(['yum', 'install', '-y', 'git'])

        # composer is a bit more complicated
        if self.config['php']['install'] and self.config['php']['composer']:
            expected_sig = self.procOpenPipe(['wget',  '-qO', '-', 'https://composer.github.io/installer.sig']).stdout.read().strip()
            self.call(['wget', '-qO', self.pwd+'/composer-setup.php', 'https://getcomposer.org/installer'])
            actual_sig = self.procOpenPipe(['php', '-r', "echo hash_file('SHA384', '"+self.pwd+"/composer-setup.php');"]).stdout.read().strip()

            if expected_sig != actual_sig:
                raise Exception('Error installing composer; expected sig - "'+expected_sig+'", but got sig - "'+actual_sig+'"')
            else:
                self.call(['php', self.pwd+'/composer-setup.php', '--quiet'])
                self.call(['mv', self.pwd+'/composer.phar', '/usr/local/bin/composer'])

            self.call(['rm', self.pwd+'/composer-setup.php'])

        print 'OK'
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

    def initFpm( self ):
        print 'Bootstrapping FPM sites...'

        self.call(['cp', self.pwd+'/nginx.conf', '/etc/nginx/nginx.conf'])
        self.call(['mkdir', '/etc/nginx/sites-available'])
        self.call(['mkdir', '/etc/nginx/sites-enabled'])
        self.call(['chmod', '775', '/etc/nginx/sites-available'])
        self.call(['chmod', '755', '/etc/nginx/sites-enabled'])

        for fpm_site in self.config['nginx']['fpm_sites']:
            replacements = {
                '@@USER@@': fpm_site['user'],
                '@@SOCKET@@': fpm_site['socket'],
                '@@HOSTNAME@@': fpm_site['hostname']
            }

            # create and template the file
            Provizzen.replaceInFile(replacements, self.pwd+'/vhost.conf', '/etc/nginx/sites-available/'+fpm_site['user']+'.conf')
            Provizzen.replaceInFile(replacements, self.pwd+'/pool.conf', '/etc/php-fpm.d/'+fpm_site['user']+'.conf')

            # change permissions
            self.call(['chmod', 'g+rx', '/home/'+fpm_site['user']])
            self.call(['chmod', '600', '/etc/nginx/sites-available/'+fpm_site['user']+'.conf'])
            self.call(['ln', '-s', '/etc/nginx/sites-available/'+fpm_site['user']+'.conf', '/etc/nginx/sites-enabled/'+fpm_site['user']+'.conf'])

            # create the necessary directories
            self.call(['mkdir', '-p', '/home/'+fpm_site['user']+'/www/public'])
            self.call(['mkdir', '/home/'+fpm_site['user']+'/logs'])
            self.call(['mkdir', '/home/'+fpm_site['user']+'/sessions'])

            # set appropriate
            self.call(['chmod', '-R', '750', '/home/'+fpm_site['user']])
            self.call(['chmod', '700', '/home/'+fpm_site['user']+'/sessions'])
            self.call(['chmod', '770', '/home/'+fpm_site['user']+'/logs'])
            self.call(['chmod', '-R', '750', '/home/'+fpm_site['user']+'/www'])

        # reload fpm and nginx


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

    def initPHP( self ):
        print 'Bootstrapping PHP...'

        self.call(['wget', '-qO', self.pwd+'/setup-ius.sh', 'https://setup.ius.io/'])
        self.call(['bash', self.pwd+'/setup-ius.sh'])

        if self.config['php']['version'] == '7.0':
            self.call(['yum', 'install', '-y', 'php70u-fpm-nginx', 'php70u-cli', 'php70u-mysqlnd', 'php70u-json', 'php70u-mbstring', 'php70u-xml'])
        elif self.config['php']['version'] == '7.1':
            self.call(['yum', 'install', '-y', 'php71u-fpm-nginx', 'php71u-cli', 'php71u-mysqlnd', 'php71u-json', 'php71u-mbstring', 'php71u-xml'])
        else:
            raise Exception('Invalid PHP version: '+self.config['php']['version'])

        self.call(['rm', self.pwd+'/setup-ius.sh'])

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

    def call( self, call_args ):
        with open(self.pwd+'/output.log', 'a') as logfile:
            ret = subprocess.call(call_args, stdout=logfile, stderr=subprocess.STDOUT, env=os.environ)

        return ret

    def procOpenPipe( self, call_args ):
        return subprocess.Popen(call_args,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ
        )

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

    @staticmethod
    def replaceInFile( replacements, src, dest=None):
        filedata = None

        if dest == None:
            dest = src

        with open(src, 'r') as file:
            filedata = file.read()

        for searchkey, value in replacements.iteritems():
            filedata = filedata.replace(searchkey, value)

        with open(dest, 'w') as file:
            file.write(filedata)

        return

if __name__ == '__main__':
    # merge config file with defaults
    prov = Provizzen({
        'users': [],
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
            'composer': True,
            'version': '7.1'
        },
        'skel': [
            {'type': 'dir', 'mode': '700', 'path': '.ssh'},
            {'type': 'file', 'mode': '600', 'path': '.ssh/authorized_keys'}
        ]})
    prov.setConfigFromFile()
    prov.bootstrap()

