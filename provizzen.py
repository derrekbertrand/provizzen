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

        return

    def bootstrap( self ):
        if self.config == None:
            raise Exception('You must load a config before bootstrapping your system!')

        self.initEpel()
        self.initFirewall()
        self.initSkel()
        self.initSshd()
        # bootstrap_users()
        # bootstrap_updates()
        self.initMotd()

        return

    def initEpel( self ):
        print 'Bootstrapping EPEL...'

        subprocess.call('yum', 'install', '-y', 'epel-release')

        print 'OK'
        return

    def initFirewall( self ):
        print 'Bootstrapping firewalld...'

        subprocess.call('yum', 'install', '-y', 'firewalld')
        subprocess.call('systemctl', 'start', 'firewalld')
        subprocess.call('systemctl', 'enable', 'firewalld')


        subprocess.call('firewall-cmd', '--permanent', '--remove-service=dhcpv6-client')
        subprocess.call('firewall-cmd', '--permanent', '--remove-service=ssh')

        # add the port from sshd config
        subprocess.call('firewall-cmd', '--permanent', '--add-port='+self.config['sshd']['port']+'/tcp')

        subprocess.call('firewall-cmd', '--reload')

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

    # this makes sure we have the files necessary for SSH
    def initSkel( self ):
        print 'Bootstrapping skel...'

        for skel in self.config['skel']:
            if skel['type'] == 'dir':
                skel = Provizzen.mergeConfig({'type': 'dir', 'mode': '755', 'path': 'your_admin_botched_skel'}, skel)
                subprocess.call(['mkdir', '-p', '/etc/skel/'+skel['path']])
                subprocess.call(['chmod', skel['mode'], '/etc/skel/'+skel['path']])
            elif skel['type'] == 'file':
                skel = Provizzen.mergeConfig({'type': 'file', 'mode': '644', 'path': 'your_admin_botched_skel'}, skel)
                subprocess.call(['touch', '/etc/skel/'+skel['path']])
                subprocess.call(['chmod', skel['mode'], '/etc/skel/'+skel['path']])
            else:
                raise Exception('Skel type must be "dir" or "file"; "%s" given' % str(skel['type']))

        print 'OK'
        return

    def initSshd( self ):
        print 'Bootstrapping SSH policy...'

        Provizzen.sedIE('^(#?)PasswordAuthentication .+$', 'PasswordAuthentication no', '/etc/ssh/sshd_config')
        Provizzen.sedIE('^(#?)ChallengeResponseAuthentication .+$', 'ChallengeResponseAuthentication no', '/etc/ssh/sshd_config')
        Provizzen.sedIE('^(#?)Port .+$', 'Port '+self.config['sshd']['port'], '/etc/ssh/sshd_config')
        # if we are setting up users, then don't allow root access
        if self.config['sshd']['disable_root']:
            Provizzen.sedIE('^(#?)PermitRootLogin .+$', 'PermitRootLogin no', '/etc/ssh/sshd_config')
        else:
            print '- Allowing remote access as root, like a moron'

        subprocess.call('systemctl', 'restart', 'sshd.service')

        print 'OK'
        return

    def initUpdates( self ):
        print 'Bootstrapping updates...'

        # do an update now
        subprocess.call('yum', 'update', '-y')

        # install yum-cron to automatically update the server
        subprocess.call('yum', 'install', '-y', 'yum-cron')
        Provizzen.sedI('update_cmd', 'update_cmd = security', '/etc/yum/yum-cron.conf')

        # sed -i '/update_cmd/c\update_cmd = security' /etc/yum/yum-cron.conf
        # sed -i '/apply_updates/c\apply_updates = yes' /etc/yum/yum-cron.conf
        # systemctl start yum-cron
        # systemctl enable yum-cron

        print 'OK'
        return

    def bootstrap_users( config ):
        print 'Bootstrapping user accounts...'

        if 'users' in config:
            handle_users(config['users'])

            #lock the root account, this is done by default if you have users
            if 'disable_root' in config:
                assert type(config['disable_root']) == bool
                if(config['disable_root']):
                    subprocess.call(['passwd', '-l', 'root'])
            else:
                subprocess.call(['passwd', '-l', 'root'])

        # note that we don't lock root if we don't have a users config group
        print 'OK'
        return

    def handle_users( users ):
        # check over the user data
        validate_users(users)

        # we know they're all valid, create them
        for user in users:
            # create user; set password
            subprocess.call(['adduser', user['name']])
            p = subprocess.Popen(['passwd', user['name'], '--stdin'], stdout=PIPE, stdin=PIPE, stderr=PIPE)
            p.communicate(input=user['pass'])

            # check if we need to add this user to any groups
            if 'groups' in user:
                handle_user_groups( user )

            # add the user's keys
            handle_user_keys( user )

        return

    def validate_users( users ):
        assert type(users) == list
        for user in users:
            assert 'name' in user
            assert 'pass' in user
            assert 'ssh-keys' in user
            assert type(user['name']) == str
            assert type(user['pass']) == str
            assert type(user['ssh-keys']) == list
            for key in user['ssh-keys']:
                assert type(key) == str

            #optional arguments
            if 'groups' in user:
                for group in user['group']:
                    assert type(group) == str

        return

    def handle_user_groups( user ):
        for group in user['groups']:
            subprocess.call(['usermod', '-a', '-G', group, user['name']])

        return

    def handle_user_keys( user ):
        keyfile = open('/home/'+user['name']+'/.ssh/authorized_keys', 'a')

        for key in user['ssh-keys']:
            keyfile.write(key)

        keyfile.close()

        return

    @staticmethod
    def sedI( search, replace, filename ):
        return subprocess.call([
            'sed',
            '-i',
            "'/"+search+"/c\\"+replace+"'",
            filename
        ])

    @staticmethod
    def sedIE( regex, replace, filename ):
        return subprocess.call([
            'sed',
            '-i',
            '-E',
            '"s/'+regex+'/'+replace+'/"',
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
        'sshd': {'port': '12222', 'disable_root': False},
        'skel': [
            {'type': 'dir', 'mode': '700', 'path': '.ssh'},
            {'type': 'file', 'mode': '600', 'path': '.ssh/authorized_keys'}
        ]})
    prov.setConfigFromFile()
    prov.bootstrap()

