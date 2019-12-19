#coding: utf-8

import os, subprocess, sys
import threading, time, datetime
import logging, argparse
from inter.packageinfo_get import getpkg as packageinfo_get_getpkg
import urllib.request
import zipfile

logging.basicConfig(level = logging.INFO, format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)d]: %(message)s')
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.ERROR)


def execShellDaemon(cmd):
    return subprocess.Popen(cmd, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)

def execShell(cmd, t=120):
    ret = {}
    try:
        p = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, shell=True, encoding='utf-8', timeout=t)
        if p.returncode == 0:
            ret['d'] = p.stdout
        else:
            ret['e'] = p.stderr
    except subprocess.TimeoutExpired:
        ret['e'] = 'timeout'

    return ret

def downloadFile(url, savepath):
    try:
        urllib.request.urlretrieve(url, savepath)
        return True
    except Exception as e:
        logging.info(str(e))
        return False

def isDexExist(apk):
    zipf = zipfile.ZipFile(apk)
    if 'classes.dex' in zipf.namelist():
        return True
    return False

def getDexFromVdex(curdir, path, adb, sp):
    d = os.path.dirname(path)
    n = os.path.basename(d)+'.vdex'
    dt = d+'/oat/arm/'+n
    # pull vdex
    cmd = adb + ' pull '+dt+' '+sp
    ret = execShell(cmd)
    #print(ret)
    if 'e' in ret.keys():
        dt = d+'/oat/arm64/'+n
        cmd = adb + ' pull '+dt+' '+sp+'.vdex'
        ret = execShell(cmd)
    if os.path.isfile(sp+'.vdex'):
        # android pie 9, multi dex
        # convert to cdex
        cmd = curdir+'/inter/vdexExtractor  -f  -i '+sp+'.vdex '+' -o '+curdir+'/apps/tmp'
        ret = execShell(cmd)
        pkg = os.path.basename(sp)
        cdex = False
        for f in os.listdir(curdir+'/apps/tmp'):
            if pkg+'_classes' in f and '.cdex' in f:
                cdex = True
                # cdex to dex
                cmd = curdir+'/inter/compact_dex_converters  '+curdir+'/apps/tmp/'+f
                ret = execShell(cmd)

        zipf = zipfile.ZipFile(sp+'.apk', 'a')
        for f in os.listdir(curdir+'/apps/tmp'):
            if cdex and '.new' in f and pkg+'_classes' in f:
                # com.miui.fm_classes.cdex.new
                zipf.write(curdir+'/apps/tmp/'+f, f.split('_')[1].split('.')[0]+'.dex')

            elif not cdex and '.dex' in f and pkg+'_classes' in f:
                # com.miui.fm_classes.dex
                zipf.write(curdir+'/apps/tmp/'+f, f.split('_')[1])
        zipf.close()

        os.remove(sp+'.vdex')
        for f in os.listdir(curdir+'/apps/tmp'):
            os.remove(curdir+'/apps/tmp/'+f)
        
    else:
        logging.error('dex and vdex not exist')

def downloadPkgList(adb, pkgList, devicePkg):
    logging.info('======Download======')

    curdir = os.path.dirname(os.path.abspath(__file__))
    try:
        os.mkdir(curdir+'/apps')
    except:
        pass
    try:
        os.mkdir(curdir+'/apps/tmp')
    except:
        pass
    for p in pkgList:
        logging.info('=='+p)
        sp = curdir+'/apps/'+p
        if os.path.isfile(sp+'.apk'):
            
            if isDexExist(sp+'.apk'):
                isnew = False
                ver = getVersionNameApk(p)
                
                if not ver:
                    logging.error('get apk version error')
                    #获取本地version错误，不重新下载
                    isnew = True
                else:
                    #考虑预置APP和安装的外发APP
                    over = getVersionNameOnline(p)
                    
                    if over:
                        tover = over.split(':')
                        if len(tover) == 2:
                            # 检查是否半年未更新
                            lastupdate = datetime.datetime.now() - datetime.timedelta(days = 180)
                            lastupdate = lastupdate.strftime("%Y-%m-%d")
                            if lastupdate > tover[1]:
                                logging.info('!!outdated')
                                execShell('rm '+sp+'.apk')
                                continue
                            if ver and ver >= tover[0]:
                                isnew = True
                    else:       
                        dver = getVersionNameDevice(adb, p)
                        if dver:
                            if ver and ver >= dver:
                                isnew = True
                    
                    if isnew:
                        logging.info('exists')
                        continue
                    logging.info('old version')
            
            execShell('rm '+sp+'.apk')

        #从设备拉，组装vdex
        if not os.path.isfile(curdir+'/inter/compact_dex_converters'):
            logging.error('please download cdex convertor first: https://pan.mioffice.cn:443/link/AEB39658B994645AE544E6C13730CD34  and 保存到inter目录下')
            return
        if p in devicePkg:
            cmd = adb + ' shell "pm path  '+p+'"'
            ret = execShell(cmd)
            if 'd' in ret.keys():
                path = ret.get('d').split(':')[1].strip()
                logging.info('Pull from device')
                cmd = adb + ' pull '+path+' '+sp
                ret = execShell(cmd)
                if 'd' in ret.keys():
                    execShell('mv '+sp+' '+sp+'.apk')
                    if not isDexExist(sp+'.apk'):
                        getDexFromVdex(curdir, path, adb, sp)
                else:
                    logging.error('pull error'+ret.get('e'))
        else:
            #下载
            url = packageinfo_get_getpkg(p, False)
            if url :
                logging.info('Downloading ')
                if downloadFile(url, sp+'.tmp'):
                    ret = execShell('mv '+sp+'.tmp '+sp+'.apk')
                else:
                    logging.info('Downlod error ')
            else:
                logging.info('!!pkgname not exists')
        
    logging.info('====Download done====')

def getinstallmks(adb):
    out = '''
    count=100
    speed=1.0
    start data >>

    DispatchPointer(10000, 10000, 0, xpoint, ypoint, 0, 0, 0, 0, 0, 0, 0)
    DispatchPointer(10000, 10000, 1, xpoint, ypoint, 0, 0, 0, 0, 0, 0, 0)
    UserWait(7000)
    '''
    ret = execShell(adb+' shell wm size')
    if 'e' in ret.keys():
        logging.error(ret.get('e'))
        return False
    #Physical size: 1080x1920
    tmp = ret.get('d')
    tmp = tmp.split(': ')
    tmp = tmp[1]
    tmp = tmp.split('x')
    width = int(tmp[0])
    height = int(tmp[1])
    out = out.replace('xpoint', str(int(width/4)))
    out = out.replace('ypoint', str(height - 150))
    
    ret = execShell(adb+' shell "echo \' '+out+'\' >/sdcard/install.mks"')
    if 'e' in ret.keys():
        logging.error(ret.get('e'))
        return False

    return True

def getPermissionPid(adb):
    p = 'com.lbe.security.miui:ui'
    tpcmd = adb + ' shell "ps -A | grep '+p+'" '
    ret = execShell(tpcmd)
    if 'd' in ret.keys():
        data = ret.get('d').split('\n')
        for d in data:
            tmp = d.split()
            if len(tmp) == 9 and tmp[8] == p:
                return tmp[1]
    return ''

def killPermissionRequest(adb, deviceid):
    #进程需要权限请求激活，第一个app可能权限绕不过
    p = 'com.lbe.security.miui:ui'
    curdir = os.path.dirname(os.path.abspath(__file__))
    tpcmd = adb + ' shell "ps -A | grep '+p+'" '
    while True:
        ret = execShell(tpcmd)
        if 'd' in ret.keys():
            data = ret.get('d').split('\n')
            for d in data:
                tmp = d.split()
                if len(tmp) == 9 and tmp[8] == p:
                    logging.info('==Hook '+p+'  pid:'+tmp[1])
                    if deviceid:
                        cmd = 'frida -D ' + deviceid+' '
                    else:
                        cmd = 'frida -U '
                        
                    cmd += ' --no-pause -l '+curdir+'/inter/kill_permission_request.js -p '+tmp[1]
                    frida = execShellDaemon(cmd)
                    
                    while not frida.poll():
                        time.sleep(10)

def killMonkey(adb):
    logging.info('Clean monkey')
    cmd = adb + ' shell "ps -A | grep com.android.commands.monkey" '
    ret = execShell(cmd)
    if 'd' in ret.keys():
        data = ret.get('d').split('\n')
        for d in data:
            tmp = d.split()
            if len(tmp) == 9 and tmp[8] == 'com.android.commands.monkey':
                cmd = adb + ' shell "su -c \' kill -9 '+tmp[1]+'\' "'
                ret = execShell(cmd)
                if 'e' in ret.keys():
                    logging.info(ret.get('e'))

    logging.info('Clean monkey done')
    
def startMonekyTest(adb, pkgList, devicePkg, deviceid):
    installPkg(adb, pkgList, devicePkg)
    devicePkg = getDevicePkgs(adb)
    from inter.apkcookpy.lib.apk import APKCook
    logging.info('=====start monkey=====')
    blacklist = [
        'com.android.settings',
        'com.topjohnwu.magisk'
    ]
    #设置selinux
    #cmd: Failure calling service activity: Failed transaction
    cmd = adb + ' shell "su -c \'setenforce 0\'" '
    ret = execShell(cmd)
    if 'e' in ret.keys():
        logging.error(ret.get('e'))
    
    cmd = adb + ' shell  "mkdir /sdcard/monkeylogs"'
    ret = execShell(cmd)
    
    curdir = os.path.dirname(os.path.abspath(__file__))
    frida = False
    cmd = adb + ' shell  "ps -A | grep frida"'
    ret = execShell(cmd)
    if 'd' in ret.keys():
        if ret.get('d').find('frida-helper-') != -1:
            frida = True        
    if not frida:
        logging.error('== frida server closed==')
        return
     
    if deviceid:
        _frida_ = 'frida -D '+deviceid+' '
    else:
        _frida_ = 'frida -U '

    # 权限申请hook
    # 使用thread在ctrl+C情况下，难退出
    pid = getPermissionPid(adb)
    if pid:
        logging.info('==Hook com.lbe.security.miui:ui  pid:'+pid)
        cmd = _frida_ + ' --no-pause -l '+curdir+'/inter/kill_permission_request.js -p '+pid
        permission_frida = execShellDaemon(cmd)
    
    for p in pkgList:
        if p in blacklist:
            continue
        if p not in devicePkg:
            logging.error(p+' not installed')
            continue
        #检查设备在线
        if not checkOnline(deviceid):
            logging.error('Device offline')
            return
        #准备apk文件
        sp = curdir+'/apps/'+p
        if not os.path.isfile(sp+'.apk'):
            cmd = adb + ' shell "pm path  '+p+'"'
            ret = execShell(cmd)
            if 'd' in ret.keys() and ret.get('d'):
                path = ret.get('d').split(':')[1].strip()
                logging.info('Pull from device')
                cmd = adb + ' pull '+path+' '+sp
                ret1 = execShell(cmd)
                if 'd' in ret1.keys():
                    execShell('mv '+sp+' '+sp+'.apk')
                else:
                    logging.error(ret1.get('e'))
            else:
                logging.error(ret.get('e'))
        
        
        if not os.path.isfile(sp+'.apk'):
            logging.error(p+'.apk not exists')
            continue
        
        logging.info('=='+p)
            
        # frida unload ssl
        cmd =  _frida_ + ' --no-pause -l '+curdir+'/inter/unload_ssl.js -f '+p
        ssl_frida = execShellDaemon(cmd)

        # permission hook
        if not pid:
            pid = getPermissionPid(adb)
            if pid:
                alive = True
                try:
                    if permission_frida.poll():
                        alive = False
                except Exception:
                    alive = False
                if not alive:
                    logging.info('==Hook com.lbe.security.miui:ui  pid:'+pid)
                    cmd = _frida_ + ' --no-pause -l '+curdir+'/inter/kill_permission_request.js -p '+pid
                    permission_frida = execShellDaemon(cmd)

        #解析activity/service组件
        encrypt = False
        try:
            # has exception
            activity = APKCook(sp+'.apk').show('a')
            if len(activity) < 2:
                encrypt = True

            #防止单个activity卡死
            timeout = 60
            timeoutThread = threading.Thread(target=timeoutKIll, args=(adb, p, timeout), daemon=True)
            timeoutThread.start()

            cmd = adb + ' shell  "rm /sdcard/monkeylogs/'+p+'.log"'
            ret = execShell(cmd)

            for a in activity:
                logging.info(a)
                cmd = adb + ' shell "su -c \'am start -n '+p+'/'+a+'\' " '
                #timeout not working, because connected to pipe
                execShell(cmd, 20)

                cmd = adb + ' shell "su -c \'monkey -p '+p+' -vvv  --throttle 100 --pct-syskeys 0  --ignore-crashes 133 >> /sdcard/monkeylogs/'+p+'.log\' " '
                execShell(cmd, 20)
                if not timeoutThread.is_alive():
                    timeoutThread = threading.Thread(target=timeoutKIll, args=(adb, p, timeout), daemon=True)
                    timeoutThread.start()

            service = APKCook(sp+'.apk').show('s')
            for s in service:
                logging.info(s)
                cmd = adb + ' shell "su -c \'am start-service  '+p+'/'+s+'\' " '
                execShell(cmd, 20)
                time.sleep(1)

            receiver = APKCook(sp+'.apk').show('r')
            for s in receiver:
                logging.info(s)
                cmd = adb + ' shell "su -c \'am broadcast  '+p+'/'+s+'\' " '
                execShell(cmd, 20)
                time.sleep(1)

        except KeyboardInterrupt:
            try:
                permission_frida.terminate()
            except Exception:
                pass
            ssl_frida.terminate()
            cmd = adb + ' shell "am force-stop '+p+' " '
            ret = execShell(cmd)
            raise KeyboardInterrupt

        except Exception as e:
            # import traceback
            # traceback.print_exc()
            logging.error(str(e))
            encrypt = True
        
        if encrypt:
            cmd = adb + ' shell "su -c \'monkey -p '+p+' -vvv  --throttle 100 --pct-syskeys 0  --ignore-crashes 1333 >> /sdcard/monkeylogs/'+p+'.log\' " '
            ret = execShell(cmd)
            # if 'e' in ret.keys():
            #     logging.info(ret.get('e'))

        cmd = adb + ' shell "am force-stop '+p+' " '
        ret = execShell(cmd)
        ssl_frida.terminate()
        time.sleep(0.2)
        # cmd = adb + ' shell \' su -c "am force-stop '+p+' "\' '
        # ret = execShell(cmd)

def timeoutKIll(adb, p, t):
    for i in range(t):
        time.sleep(1)
    cmd = adb + ' shell "am force-stop '+p+' " '
    execShell(cmd)

def installPkg(adb, pkgList, devicePkg):
    downloadPkgList(adb, pkgList, devicePkg)
    logging.info('======install======')

    #install monkey
    if not getinstallmks(adb):
        logging.error('Install mks error')
        return
    installmcmd = adb + ' shell "su -c \' monkey -f /sdcard/install.mks 1000\'" '
    installm = execShellDaemon(installmcmd)
    ##

    curdir = os.path.dirname(os.path.abspath(__file__))
    for p in pkgList:
        logging.info('=='+p)
        if p in devicePkg:
            #logging.info('exists')
            continue
        
        if not os.path.isfile(curdir+'/apps/'+p+'.apk'):
            logging.error('apk error')
            continue

        if installm.poll():
            installm = execShellDaemon(installmcmd)
        logging.info('Installing ')
        cmd = adb + ' install '+curdir+'/apps/'+p+'.apk'
        ret = execShell(cmd)
        if 'e' in ret.keys():
            logging.error(ret.get('e'))
        else:
            logging.info('Install success')

    #清理monkey     
    installm.terminate()
    time.sleep(1)
    killMonkey(adb)

    logging.info('======Install done======')

def uninstallPkg(adb, pkgList, devicePkg):
    for p in pkgList:
        logging.info('Uninstalling '+p)
        if p in devicePkg:
            # always return true
            cmd = adb + '  shell pm  uninstall '+p
            ret = execShell(cmd)
            if ret.get('d'):
                logging.info('Uninstall succ')
            else:
                logging.error('Uninstall error')
            
        else:
            logging.error("not installed ")

def getVersionNameDevice(adb, pkg):
    cmd = adb + ' shell "dumpsys package '+pkg+'  | grep versionName" '
    ret = execShell(cmd)
    if ret.get('d'):
        vs = ret.get('d').split('\n')
        for v in vs:
            if v:
                vv = v.split('=')
                if len(vv) == 2:
                    return vv[1]
    return False

def getVersionNameApk(pkg):
    from inter.apkcookpy.lib.apk import APKCook
    curdir = os.path.dirname(os.path.abspath(__file__))
    try:
        return APKCook(curdir+'/apps/'+pkg+'.apk').show('v')
    except:
        return False

def getVersionNameOnline(pkg):
    return packageinfo_get_getpkg(pkg, True, True)

def checkOnline(deviceid=''):
    devices = execShell('adb devices -l').get('d').split('\n')
    ret = [d for d in devices if d.find('device ') != -1]
    dids = [d.split()[0] for d in ret]
    if deviceid:
        if deviceid in dids:
            return True
        else:
            print('Device id error')
            print(execShell('adb devices -l').get('d'))
            return False
    else:
        if len(dids) == 0:
            print('No device')
            return False
        elif len(dids) == 1:
            return True
        elif len(dids) > 1:
            print('More than one device, please set -s deviceid')
            return False

def getPkgListFromFile(p):
    if os.path.isfile(p):
        try:
            with open(p, 'r') as f:
                pkgs = f.read().split('\n')
        except Exception as e:
            logging.info(str(e))
            pkgs = []
    else:
        pkgs = p.split(',')
    pkg = []
    for p in pkgs:
        if p:
            pkg.append(p.strip())
    return pkg

def getDevicePkgs(adb):
    ret = execShell(adb + ' shell pm list packages')
    pkgs = []
    if 'e' not in ret.keys():
        dt = ret.get('d').split('\n')
        for p in dt:
            if p:
                pkgs.append(p.split(':')[1])
    else:
        logging.error(ret.get('e'))
    return pkgs
    
def getPkgListInternet(pkg):
    return packageinfo_get_getpkg(pkg, True)

def getExport(pkg):
    p = []
    curdir = os.path.dirname(os.path.abspath(__file__))
    if os.path.isfile(pkg) and '.apk' in pkg:
        p.append(pkg)
    elif os.path.isfile(curdir+'/apps/'+pkg+'.apk'):
        p.append(curdir+'/apps/'+pkg+'.apk')
    elif os.path.isfile(pkg):
        pp = getPkgListFromFile(pkg)
        for t in pp:
            p.append(curdir+'/apps/'+t+'.apk')

    for pp in p:
        try:
            from inter.apkcookpy.lib.apk import APKCook
            APKCook(pp).show()
        except:
            logging.error('=error '+pp)
    
def getAndroidruntime(p, adb):
    cmd = 'pidcat -v'
    ret = execShell(cmd)
    if 'e' in ret.keys():
        logging.error('Install pidcat first')
        return
    curdir = os.path.dirname(os.path.abspath(__file__))
    pkg = curdir+'/apps/'+p+'.apk'
    if os.path.isfile(pkg):
        cmd = 'pidcat '+p+' -c -l E -t AndroidRuntime >'+p+'.log'
        logp = execShellDaemon(cmd)
        from inter.apkcookpy.lib.apk import APKCook
        a = APKCook(pkg).show('ma')
        s = APKCook(pkg).show('ms')
        r = APKCook(pkg).show('mr')
        for ai in a.split(','):
            print(ai)
            cmd = adb + ' shell "am start -n '+p+'/'+ai+' " '
            execShell(cmd, 20)
            time.sleep(2)
        
        for ai in s.split(','):
            print(ai)
            cmd = adb + ' shell "am start-service -n '+p+'/'+ai+' " '
            execShell(cmd, 20)
            time.sleep(0.5)

        for ai in r.split(','):
            print(ai)
            cmd = adb + ' shell "am broadcast -n '+p+'/'+ai+' " '
            execShell(cmd, 20)
            time.sleep(0.5)

        time.sleep(2)
        logp.terminate()
        print('see logfile: '+p)
    else:
        print('apk error')

def getPortapp(adb):
    print('Getting device listen port...')
    if isPhoneRooted(adb):
        cmd = adb + ' shell " su  -c \'netstat -tpln | grep LISTEN\'"'
        ret = execShell(cmd)
        if 'd' in ret.keys():
            info = ret.get('d').strip('\n').split('\n')
            for  i in info:
                port = i.split()[3]
                name = i.split()[6].split('/')[1]
                print(name+'>'+port)
        return

    #not rooted   
    cmd = adb + ' shell "netstat -tpln | grep LISTEN"'
    ret = execShell(cmd)
    
    if 'd' in ret.keys():
        netstats = ret.get('d').strip('\n').split('\n')
        for t in netstats:
            #print(t.split())
            ipportres = t.split()[3]
            #print(ipportres)
            ipport = ipportres.split(':')
            ipportlen = len(ipport)
            if ipportlen == 2:
                port = hex(int(ipport[1]))   
            else:
                #tcp6
                port = hex(int(ipport[ipportlen - 1]))

            port = port.replace('0x', '')
            if ipportlen == 2:
                cmd = adb +' shell "cat /proc/net/tcp | grep -i '+port+'"'
            else:
                #tcp6
                cmd = adb +' shell "cat /proc/net/tcp6 | grep -i '+port+'"'
            
            ret = execShell(cmd)
            #print(ret)
            if 'd' in ret.keys():
                tcps = ret.get('d').strip('\n').split('\n')
                
                for t in tcps:
                    uid = t.split()[7]
                    if uid == '0':
                        print(ipportres + ' system uid:0')
                    else:
                        cmd = adb +' shell "pm list package --uid '+uid+'"'
                        ret = execShell(cmd)
                        #print(ret)
                        if 'd' in ret.keys():
                            print(ipportres + ' '+ret.get('d').strip('\n'))
                        else:
                            print(ipportres + ' pkg error')
                    break


def getCallstack(m, callstack, count):
    ##
    #获取函数的调用树，全部存储callstack list
    #count 用于防止栈益处，重载函数可能溢出
    ##
    ref = m.get_xref_from()
    if not ref or len(ref) == 0:
        return
    for c,m,_ in ref:
        callstack.append(c.name+':'+m.name)
        if count[0] > 500:
            #print('====max '+c.name+':'+m.name)
            return
        count[0] = count[0]+1
        getCallstack(c.get_method_analysis(m), callstack, count)


def getParents(dx, c):
    ss = []
    cc = c
    while cc and cc.extends != 'Ljava/lang/Object;':
        ss.append(cc.extends)
        cc = dx.classes.get(cc.extends)
    return ss

def runAndroguard(pkgs):
    #导入androguard
    try:
        from androguard import misc
    except:
        logging.error('Install androguard first')
        return
    from inter.apkcookpy.lib.apk import APKCook
    curdir = os.path.dirname(os.path.abspath(__file__))
    for p in pkgs:
        try:
            logging.info('=='+p)
            pkg = curdir+'/apps/'+p+'.apk'
            if not os.path.isfile(pkg):
                logging.error('file not exists')
                continue
            #获取Browsable Activity
            bs = APKCook(pkg).show('b')
            browsable_activities = ['L'+b.replace('.', '/')+';' for b in bs]
            blen = len(browsable_activities)
            logging.info('browsable activities: '+str(blen))
            if blen < 1:
                continue
            logging.info('androguard analysing')
            a, d, dx = misc.AnalyzeAPK(pkg)
            
            browsable_activities_t = []
            for b in browsable_activities:
                b = dx.classes.get(b)
                if b:
                    browsable_activities_t.extend(getParents(dx, b))
            browsable_activities.extend(browsable_activities_t)
            browsable_activities = list(set(browsable_activities))
            logging.info('browsable activities plus: '+str(blen))
            
            
            print('=browsable - loadUrl:')
            #继承实现
            for c in dx.get_classes():
                ss = getParents(dx, c)
                if 'Landroid/webkit/WebView;' in ss:
                    for m in c.get_methods():
                        if m.name == 'loadUrl':
                            cs = []
                            count = [0]
                            getCallstack(m, cs, count)
                            cs = list(set(cs))
                            for r in cs:
                                if r.split(':')[0] in browsable_activities:
                                    print(r)
                                    
            ###实例调用
            for m in dx.classes['Landroid/webkit/WebView;'].get_methods():
                if m.name == 'loadUrl':
                    cs = []
                    count = [0]
                    getCallstack(m, cs, count)
                    cs = list(set(cs))
                    for r in cs:
                        if r.split(':')[0] in browsable_activities:
                            print(r)

            print('=browsable - getIntent:')
            ###实例调用: activity.getIntent()
            getintent = dx.get_method_analysis_by_name('Landroid/app/Activity;', 'getIntent', '()Landroid/content/Intent;')
            cs = []
            count = [0]
            getCallstack(getintent, cs, count)
            cs = list(set(cs))
            for r in cs:
                if r.split(':')[0] in browsable_activities:
                    print(r)
                

            #继承实现: getIntent()
            for c in dx.get_classes():
                ss = getParents(dx, c)
                if 'Landroid/app/Activity;' in ss:
                    for m in c.get_methods():
                        if m.name == 'getIntent':
                            cs = []
                            count = [0]
                            getCallstack(m, cs, count)
                            cs = list(set(cs))
                            for r in cs:
                                if r.split(':')[0] in browsable_activities:
                                    print(r)


            #静态方法
            print('=browsable - Intent.parseUri:')
            parseuri = dx.get_method_analysis_by_name('Landroid/content/Intent;', 'parseUri', '(Ljava/lang/String; I)Landroid/content/Intent;')
            cs = []
            count = [0]
            getCallstack(m, cs, count)
            cs = list(set(cs))
            for r in cs:
                if r.split(':')[0] in browsable_activities:
                    print(r)

            
            ############

            print('done '+p)
        except Exception as e:
            import traceback
            traceback.print_exc()
            logging.error(p+ ' error: '+str(e))

def isPhoneRooted(adb):
    cmd = adb + ' shell "su -c \'id\'"'
    ret = execShell(cmd)
    return 'd' in ret.keys()

def apktool_caller(pkg):
    curdir = os.path.dirname(os.path.abspath(__file__))
    try:
        print(pkg)
        if os.path.isdir(curdir+'/appsource/'+pkg):
            print('already done')
            return
        if not os.path.isfile(curdir+'/apps/'+pkg+'.apk'):
            print(pkg+' not exist')
            return
        cmd = 'apktool d -f -r -o '+curdir+'/appsource/'+pkg+' '+curdir+'/apps/'+pkg+'.apk'
        ret = execShell(cmd, 600)
        if 'e' in ret.keys():
            print(ret.get('e'))
        else:
            print(pkg+' done')
    except Exception as e:
        print(str(e)+str(ret))

def dir_scanner(path):
    try:
        for d in os.listdir(path):
            if d.startswith('smali'):
                target_file = path+'/'+d+'/com/xiaomi/mipush/sdk/PushMessageHandler.smali'
                #print(target_file)
                if os.path.isfile(target_file):
                    ct = open(target_file, 'r').read()
                    target = 'com.xiaomi.mipush.sdk.HYBRID_NOTIFICATION_CLICK'
                    if target in ct:
                        print('Found '+os.path.basename(path))
                    
    except Exception as e:
        pass

def sourceScan(pkgs):
    from multiprocessing.dummy import Pool as ThreadPool
    curdir = os.path.dirname(os.path.abspath(__file__))
    try:
        os.mkdir(curdir+'/appsource')
    except:
        pass

    #apktool decompile
    with ThreadPool(5) as tp:
        tp.map(apktool_caller, pkgs)
    
    print('==scanning')
    #scan
    pathlist = []
    for p in pkgs:
        pathlist.append(curdir+'/appsource/'+p)
    with ThreadPool(5) as tp:
        tp.map(dir_scanner, pathlist)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='批量启动APP工具(推荐Linux系统)')
    parser.add_argument("-m", "--monkey", type=str, help="monkey测试，输入包名或文件名(包名以逗号分隔，文件中按行保存包名)")
    parser.add_argument("-i", "--install", type=str, help="批量安装，输入包名或文件名")
    parser.add_argument("-u", "--uninstall", type=str, help="批量卸载，输入包名或文件名")
    parser.add_argument("-l", "--lists", type=str, help="搜索包名相关APP，输入包名前缀或完整包名")
    parser.add_argument("-d", "--download", type=str, help="批量下载，输入包名或文件名")
    parser.add_argument("-s", "--deviceid", type=str, help="指定设备（连接多个手机情况下）")
    parser.add_argument("-c", "--clean", action="store_true", help="清理残余进程")

    parser.add_argument("-e", "--export", type=str, help="获取 APK导出组件, apk文件或包名或文件名")
    parser.add_argument("-r", "--androidruntime", type=str, help="获取可崩溃APP的组件, 包名")
    parser.add_argument("-p", "--port", action="store_true", help="获取手机监听端口及对应APP")
    parser.add_argument("-g", "--androguard", type=str, help="androguard辅助发现漏洞, 文件名")
    parser.add_argument("--source", type=str, help="扫描源码, 文件名或包名")
    

    if sys.version_info.major != 3:
        print('Run with python3')
        sys.exit()

    args = parser.parse_args()
    monkey = args.monkey
    install = args.install
    uninstall = args.uninstall
    lists = args.lists
    download = args.download
    deviceid = args.deviceid
    clean = args.clean
    export = args.export
    androidruntime = args.androidruntime
    port = args.port
    androguard = args.androguard
    source = args.source

    
    #支持多手机连接情况
    _adb_ = 'adb'
    _deviceid_ = deviceid
    #检测手机
    if not checkOnline(_deviceid_):
        sys.exit()
    if _deviceid_:
        _adb_ += ' -s '+deviceid

    if not isPhoneRooted(_adb_):
        print('[!]phone not rooted, may not work well')

    try:
        #获取设备pkgs
        devicePkg = getDevicePkgs(_adb_)
        if len(devicePkg) < 3:
            logging.error('Device error')
            sys.exit()
        
        curdir = os.path.dirname(os.path.abspath(__file__))
        if monkey:
            pkgs = getPkgListFromFile(monkey)
            startMonekyTest(_adb_, pkgs, devicePkg, _deviceid_)

        elif install:
            pkgs = getPkgListFromFile(install)
            installPkg(_adb_, pkgs, devicePkg)

        elif uninstall:
            pkgs = getPkgListFromFile(uninstall)
            uninstallPkg(_adb_, pkgs, devicePkg)

        elif lists:
            print(getPkgListInternet(lists))

        elif download:
            pkgs = getPkgListFromFile(download)
            downloadPkgList(_adb_, pkgs, devicePkg)

        elif clean:
            killMonkey(_adb_)
        
        elif export:
            getExport(export)
        
        elif androidruntime:
            getAndroidruntime(androidruntime, _adb_)

        elif port:
            getPortapp(_adb_)

        elif androguard:
            pkgs = getPkgListFromFile(androguard)
            runAndroguard(pkgs)

        elif source:
            pkgs = getPkgListFromFile(source)
            sourceScan(pkgs)

        else:
            parser.print_help()
    except KeyboardInterrupt:
        logging.info('Ctrl+C')
        killMonkey(_adb_)