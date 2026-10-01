import threading
from traceback import print_exc
from typing import Tuple
from msgpack import packb, unpackb
#from hoshino.aiorequests import post
import aiohttp
from random import randint
from json import loads, load, dump
from hashlib import md5
from secrets import token_hex
from Crypto.Cipher import AES
from base64 import b64encode, b64decode
from ._bili_game_sdk import TryLogin
from asyncio import sleep, TimeoutError
import re
from os.path import dirname, join, exists
from os import makedirs
from copy import deepcopy
import asyncio
#from ._captcha_verifier import CaptchaVerifier

gs_apiRoot = 'http://le1-prod-all-gs-gzlj.bilibiligame.net'
gs_debugging = False
gs_curpath = dirname(__file__)
g_nowVersion = "11.7.2"
gs_versionCachePath = join(gs_curpath, 'data/version.txt')
if exists(gs_versionCachePath):
    with open(gs_versionCachePath, 'r', encoding='utf-8') as fp:
        g_nowVersion = fp.read().strip()

gs_deviceCachePath = join(gs_curpath, 'data/device.json')
_g_deviceIds = None

def GetDeviceId(account: str) -> str:
    """
    获取账号对应的 DEVICE-ID。若该账号尚无记录，则生成一个随机的 32 位
    十六进制设备号，并写入 gs_deviceCachePath 持久化。

    设备号按账号隔离：每个账号拥有独立设备号，单个设备号被封不影响其他账号；
    且重启后保持不变，避免频繁更换设备触发风控。

    Args:
        account (str): PCR账号

    Returns:
        str: 该账号的 DEVICE-ID
    """
    global _g_deviceIds
    if _g_deviceIds is None:
        try:
            with open(gs_deviceCachePath, 'r', encoding='utf-8') as fp:
                _g_deviceIds = load(fp)
        except Exception:
            _g_deviceIds = {}
    deviceId = _g_deviceIds.get(account)
    if not deviceId:
        deviceId = token_hex(16)
        _g_deviceIds[account] = deviceId
        try:
            makedirs(dirname(gs_deviceCachePath), exist_ok=True)
            with open(gs_deviceCachePath, 'w', encoding='utf-8') as fp:
                dump(_g_deviceIds, fp, indent=4, ensure_ascii=False)
        except Exception:
            pass
    return deviceId

gs_defaultHeaders = {
    'Accept-Encoding': 'gzip',
    'User-Agent': 'Dalvik/2.1.0 (Linux, U, Android 5.1.1, PCRT00 Build/LMY48Z)',
    'X-Unity-Version': '2018.4.30f1',
    'APP-VER': g_nowVersion,
    'BATTLE-LOGIC-VERSION': '4',
    'BUNDLE-VER': '',
    'DEVICE': '2',
    # DEVICE-ID 在 PcrClient.__init__ 中按账号填充分配，此处仅为占位
    'DEVICE-ID': '',
    'DEVICE-NAME': 'OPPO PCRT00',
    'EXCEL-VER': '1.0.0',
    'GRAPHICS-DEVICE-NAME': 'Adreno (TM) 640',
    'IP-ADDRESS': '10.0.2.15',
    'KEYCHAIN': '',
    'LOCALE': 'CN',
    'PLATFORM-OS-VERSION': 'Android OS 5.1.1 / API-22 (LMY48Z/rel.se.infra.20200612.100533)',
    'REGION-CODE': '',
    'RES-KEY': 'ab00a0a6dd915a052a2ef7fd649083e5',
    'RES-VER': '10002200',
    'SHORT-UDID': '0'
}


class ApiException(Exception):
    def __init__(self, message:str, code:int):
        super().__init__(message)
        self.code = code


class BiliSdkClient:
    def __init__(self, account:str, password:str, platform:int, channel:int, qqid:int = None, access_key = '', uid = ''):
        self.account = account
        self.password = password
        self.platform = platform
        self.channel = channel
        self.qqid = qqid
        self.access_key = access_key
        self.uid = uid

    async def BiliLogin(self) -> Tuple[str, str]:
        """
        B服登录。若成功则返回信息，若失败跑出异常。

        Returns:
            Tuple[str, str]: uid, accessKey
        
        Raises:
            AssertionError: code!=0。此时返回完整登录信息（str格式的dict）
            Exception: 用户名或密码错误
            CaptchaVerifier中可能抛出的异常
        """
        resp = await TryLogin(self.account, self.password, self.qqid, self.access_key, self.uid)
        assert resp['code'] == 0, resp
        return resp['uid'], resp['access_key']


async def fetch_post(url, data, headers, timeout):
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data, headers=headers, timeout=timeout) as resp:
            return await resp.content.read()
        
        
class PcrClient:
    def __init__(self, account: str, password: str, platfrom: int = 2, channel: int = 1, qqid: int = None, access_key = '', uid = ''):
        self._platform = platfrom
        self._channel = channel
        self.biliSdkClient = BiliSdkClient(account, password, platfrom, channel, qqid, access_key, uid)
        
        self._viewerId = 0
        self._headers = deepcopy(gs_defaultHeaders)
        self._headers['DEVICE-ID'] = GetDeviceId(account)
        self._headers['PLATFORM'] = str(self._platform)
        self._headers['PLATFORM-ID'] = str(self._platform)
        self._headers['CHANNEL-ID'] = str(self._channel)
        
        self.needLoginAndCheck = True
        self._needBiliLogin = True
        
        self._homeIndexCache = None
        self._loadIndexCache = None
        self._access_key = access_key
        self._uid = uid
        self._lock = asyncio.Lock()

    def get_lock(self):
        return self._lock

    async def BiliLogin(self):
        self._uid, self._access_key = await self.biliSdkClient.BiliLogin()
        self._needBiliLogin = False

    @staticmethod
    def _CreateKey() -> bytes:
        return bytes([ord('0123456789abcdef'[randint(0, 15)]) for _ in range(32)])

    @staticmethod
    def _AddTo16(b: bytes) -> bytes:
        n = len(b) % 16
        n = n // 16 * 16 - n + 16
        return b + (n * bytes([n]))

    @staticmethod
    def _Pack(data: object, key: bytes) -> bytes:
        aes = AES.new(key, AES.MODE_CBC, b'7Fk9Lm3Np8Qr4Sv2')
        return aes.encrypt(PcrClient._AddTo16(packb(data, use_bin_type=False))) + key

    @staticmethod
    def _Encrypt(data: str, key: bytes) -> bytes:
        aes = AES.new(key, AES.MODE_CBC, b'7Fk9Lm3Np8Qr4Sv2')
        return aes.encrypt(PcrClient._AddTo16(data.encode('utf8'))) + key

    @staticmethod
    def _Decrypt(data: bytes):
        data = b64decode(data.decode('utf8'))
        aes = AES.new(data[-32:], AES.MODE_CBC, b'7Fk9Lm3Np8Qr4Sv2')
        return aes.decrypt(data[:-32]), data[-32:]

    @staticmethod
    def _Unpack(data: bytes):
        data = b64decode(data.decode('utf8'))
        aes = AES.new(data[-32:], AES.MODE_CBC, b'7Fk9Lm3Np8Qr4Sv2')
        dec = aes.decrypt(data[:-32])
        return unpackb(dec[:-dec[-1]], strict_map_key=False), data[-32:]
    
    def _UpdateVersion(self, data_headers: dict) -> bool:
        """
        从 data_headers.store_url 中解析最新客户端版本号并更新 APP-VER。

        客户端版本过旧时服务器会拒绝请求，但会在 data_headers.store_url 中给出
        最新版客户端的下载地址（形如 .../gzlj_11.7.2_xxxx.apk），据此自动修正。

        Returns:
            bool: APP-VER 是否发生了变化
        """
        global g_nowVersion
        if not data_headers:
            return False
        store_url = data_headers.get('store_url', '')
        if not store_url:
            return False
        res = re.search(r"\d+\.\d+\.\d+", store_url)
        if not res:
            return False
        version = res.group(0)
        if version == g_nowVersion and self._headers.get('APP-VER') == version:
            return False
        g_nowVersion = version
        gs_defaultHeaders['APP-VER'] = version
        self._headers['APP-VER'] = version
        try:
            with open(gs_versionCachePath, "w", encoding='utf-8') as fp:
                print(version, file=fp)
        except Exception:
            pass
        print(f'pcrclient: 客户端版本已自动更新为 {version}')
        return True

    def GetAccessKey(self):
        return self._access_key
    def GetUID(self):
        return self._uid

    async def CallApi(self, apiUrl: str, postData: dict, returnDataHeader=False, raiseOnErrInData: bool = True, crypted: bool = True):
        """
        使用当前对象调用BCR API。

        Args:
            apiUrl (str): get/post的路径
            postData (dict): post的data
            returnDataHeader (bool, optional): 若为真，返回tuple(data:dict, data_header:dict)；否则仅返回data. Defaults to False.
            raiseOnErrInData (bool, optional): 若为真，当返回的data中存在server_error字段时抛出异常；否则正常返回完整data。Defaults to True.
            crypted (bool, optional): 别动. Defaults to True.

        Raises:
            ApiException: raiseOnErr==True且返回的data中存在server_error字段
            aiohttp网络传输中可能抛出的异常
            
        Returns:
            若returnDataHeader为真，返回tuple(data:dict, data_header:dict)；否则仅返回data。
        """
        async with self.get_lock():
            try:
                if apiUrl == "/home/index" and self._homeIndexCache is not None:
                    response = self._homeIndexCache
                    data = response['data']
                    data_headers = response['data_headers']
                elif apiUrl == "/load/index" and self._loadIndexCache is not None:
                    response = self._loadIndexCache
                    data = response['data']
                    data_headers = response['data_headers']
                else:
                    await sleep(0.4)
                    if gs_debugging:
                        print(f'        {self.biliSdkClient.account:<20} -> {apiUrl:<20}\n            {postData}')
                    key = PcrClient._CreateKey()
                    if self._viewerId is not None:
                        postData['viewer_id'] = b64encode(PcrClient._Encrypt(str(self._viewerId), key)) if crypted else str(self._viewerId)
                    aiohttp_url = gs_apiRoot + apiUrl
                    aiohttp_data = PcrClient._Pack(postData, key) if crypted else str(postData).encode('utf8')
                    aiohttp_headers = self._headers
                    
                    try:
                        response = await fetch_post(aiohttp_url, data=aiohttp_data, headers=aiohttp_headers, timeout=8)
                    except TimeoutError:
                        raise TimeoutError("服务器响应超时")
                    except Exception as e:
                        raise Exception(f'服务器报错：{e}')

                    response = PcrClient._Unpack(response)[0] if crypted else loads(response)
                    if gs_debugging:
                        print(f'                {str(response["data"])[:98]}')
                    
                    # 维护版本
                    data_headers = response['data_headers']
                    if "/check/game_start" == apiUrl:
                        self._UpdateVersion(data_headers)

                    # 维护对象数据
                    if data_headers.get('sid', '') != '':
                        t = md5()
                        t.update((data_headers['sid'] + 'c!SID!n').encode('utf8'))
                        self._headers['SID'] = t.hexdigest()
                    if 'request_id' in data_headers:
                        self._headers['REQUEST-ID'] = data_headers['request_id']
                    if 'viewer_id' in data_headers:
                        self._viewerId = data_headers['viewer_id']

                    data = response['data']

                    if gs_debugging:
                        curpath = join(dirname(__file__), f"debug/{self.biliSdkClient.account}/{apiUrl.replace('/', '-')}.json")
                        makedirs(dirname(curpath), exist_ok=True)
                        try:
                            debugInfo = {"apiurl": apiUrl, "request": postData, "headers": data_headers, "data": data}
                            with open(curpath, "w", encoding="utf-8") as fp:
                                #json.dump(debug_info, fp, ensure_ascii=False)
                                #debug_info_json = json.dumps(debug_info, ensure_ascii=False)
                                print(str(debugInfo).replace("'", '"'), file=fp)
                        except:
                            pass
                    if 'server_error' in data:
                        print(f'pcrclient: {apiUrl} api failed {data}')
                        # 版本过旧(status 3)时从 store_url 自动修正 APP-VER，供上层重试
                        self._UpdateVersion(data_headers)
                        self.needLoginAndCheck = True
                        self._homeIndexCache = None
                        self._loadIndexCache = None
                        if raiseOnErrInData:
                            data = data['server_error']
                            raise ApiException(data['message'], data['status'])
                    else:
                        if apiUrl == '/home/index':
                            self._homeIndexCache = response
                        elif apiUrl == '/load/index':
                            self._loadIndexCache = response
                        else: # elif apiUrl不在不会导致数据变化的白名单中：
                            self._homeIndexCache = None
                            self._loadIndexCache = None
                if returnDataHeader:
                    return data, data_headers
                else:
                    return data
            except Exception as e:
                self.needLoginAndCheck = True
                self._homeIndexCache = None
                self._loadIndexCache = None
                raise e
            

    async def LoginAndCheck(self) -> None:
        """
        检查当前账号对象的状态。若有需要，自动调用登录模块。
        没有抛出异常就是检验通过。

        Raises:
            Exception: 服务器维护中
            Exception: 该账号没过完教程
            Exception: 需重新过码验证，请重试
            self.BiliLogin()中可能抛出的异常
            self.CallApi()中可能抛出的异常
        """
        if self.needLoginAndCheck == False:
            return
        
        if self._needBiliLogin and self._access_key == '' and self._uid == '':
            await self.BiliLogin()

        if 'REQUEST-ID' in self._headers:
            self._headers.pop('REQUEST-ID')

        for attempt in range(2):
            version_before = g_nowVersion
            try:
                maintenanceStatus = await self.CallApi('/source_ini/get_maintenance_status?format=json', {}, crypted=False, raiseOnErrInData=True)
                break
            except ApiException as e:
                # status 3 = 客户端版本不匹配。CallApi 已尝试用 store_url 修正 APP-VER，
                # 若确实修正成功则重试一次，否则原样抛出。
                if attempt == 0 and e.code == 3 and g_nowVersion != version_before:
                    continue
                raise
        if 'maintenance_message' in maintenanceStatus:
            raise Exception(f'服务器维护中')

        self._headers['MANIFEST-VER'] = str(maintenanceStatus['required_manifest_ver'])
        lres = await self.CallApi('/tool/sdk_login', {'uid': str(self._uid), 'access_key': self._access_key, 'channel': str(self._channel), 'platform': str(self._platform)})
        if 'is_risk' in lres and lres['is_risk'] == 1:
            self._needBiliLogin = True
            self._access_key = ''
            self._uid = ''
            raise Exception(f'需重新过码验证，请重试')  

        gamestart = await self.CallApi('/check/game_start', {'apptype': 0, 'campaign_data': '', 'campaign_user': randint(0, 99999)})

        if not gamestart['now_tutorial']:
            raise Exception("该账号没过完教程!")

        # await self.CallApi('/check/check_agreement', {})
        self.needLoginAndCheck = False