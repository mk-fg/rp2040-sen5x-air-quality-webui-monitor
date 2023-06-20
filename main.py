import struct, machine, time

try: import network # required for wifi stuff
except ImportError: network = None

try: import uasyncio as asyncio
except ImportError: import asyncio # newer mpy naming


class AQMConf:

	wifi_ap_base = dict(
		scan_interval=20.0, check_interval=10.0 )
	wifi_ap_map = dict()

	sensor_verbose = False
	sensor_reset_on_start = False
	sensor_i2c_n = 1
	sensor_i2c_pin_sda = 23
	sensor_i2c_pin_scl = 24
	sensor_i2c_addr = 105
	sensor_i2c_freq = 0 # 0 = machine.I2C default
	sensor_i2c_timeout = 0.0 # 0 = machine.I2C default

	chart_samples = 100

p_err = lambda *a: print('ERROR:', *a)
err_fmt = lambda err: f'[{err.__class__.__name__}] {err}'


def conf_parse(conf_file):
	with open(conf_file) as src:
		sec, conf_lines = None, dict()
		for n, line in enumerate(map(str.strip, src), 1):
			if not line or line[0] in '#;': continue
			if line[0] == '[' and line[-1] == ']':
				sec = conf_lines[line[1:-1].lower()] = list()
			else:
				key, _, val = map(str.strip, line.partition('='))
				if sec is None:
					p_err(f'[conf] Ignoring line {n} before section header(s) [ {key} ]')
				else: sec.append((key, key.replace('-', '_').lower(), val))

	conf = AQMConf()
	bool_map = {
		'1': True, 'yes': True, 'y': True, 'true': True, 'on': True,
		'0': False, 'no': False, 'n': False, 'false': False, 'off': False }

	if sec := conf_lines.get('wifi'):
		ap_map = {None: conf.wifi_ap_base}
		ap_keys = dict(
			scan_interval=float, check_interval=float, key=str,
			hostname=str, channel=int, reconnects=int, txpower=float,
			mac=lambda v: v.encode(), hidden=lambda v: bool_map[v],
			pm=lambda v: network and getattr(network.WLAN, f'PM_{v}') )
		ssid, ap = None, dict()
		sec.append(('ssid', 'ssid', None)) # close last ssid= section
		for key_raw, key, val in sec:
			if key == 'country': ap_map[None][key] = val
			elif key == 'verbose': ap_map[None][key] = bool_map[val]
			elif key == 'ssid':
				if ssid and not ap:
					p_err(f'[conf.wifi] Skipping ssid without config [ {ssid} ]')
				else:
					if ssid not in ap_map: ap_map[ssid] = ap_map[None].copy()
					ap_map[ssid].update(ap, ssid=ssid)
					ap.clear()
				ssid = val
			elif key_func := ap_keys.get(key):
				try: ap[key] = key_func(val)
				except Exception as err:
					p_err(f'[conf.wifi]: Failed to process [ {ssid} ] {key_raw}=[ {val} ]: {err_fmt(err)}')
			else: p_err(f'[conf.wifi] Unrecognized config key [ {key_raw} ]')
		conf.wifi_ap_base, conf.wifi_ap_map = ap_map.pop(None), ap_map

	for sk in 'sensor', 'chart':
		if not (sec := conf_lines.get(sk)): continue
		for key_raw, key, val in sec:
			key_conf = f'{sk}_{key}'
			if (val_conf := getattr(conf, key_conf, None)) is None:
				p_err(f'[conf.{sk}] Skipping unrecognized config key [ {key_raw} ]')
			else:
				if isinstance(val_conf, bool): val = bool_map[val.lower()]
				elif isinstance(val_conf, (int, float)): val = type(val_conf)(val)
				elif not isinstance(val_conf, str): raise ValueError(val_conf)
				setattr(conf, key_conf, val)

	return conf


async def wifi_client(ap_base, ap_map):
	p_log = ap_base.get('verbose') and (lambda *a: print('[wifi]', *a))
	if cc := ap_base.get('country'): network.country(cc)
	wifi = network.WLAN(network.STA_IF)
	wifi.active(True)
	p_log and p_log('Activated')

	ap_conn = ap_reconn = None
	ap_keys = [ 'ssid', 'key', 'hostname', 'pm',
		'channel', 'reconnects', 'txpower', 'mac', 'hidden' ]
	while True:
		if not (st := wifi.isconnected()):
			p_log and p_log(
				f'Not-connected (reconnect={(ap_reconn or dict()).get("ssid", "no")})' )
			ap_conn = None
			if ap_reconn: # reset same-ssid conn once on hiccups
				ap_conn, ap_reconn = ap_reconn, None
			if not ap_conn:
				ssid_set = set(ap_info[0].decode('surrogateescape') for ap_info in wifi.scan())
				p_log and p_log(f'Scan results [ {" ".join(sorted(ssid_set))} ]')
				for ssid, ap in ap_map.items():
					if ssid in ssid_set:
						ap_conn = dict(ap_base, **ap)
						break
			if ap_conn:
				p_log and p_log(f'Connecting [ {ap_conn["ssid"]} ]')
				wifi.config(**dict((k, ap_conn[k]) for k in ap_keys if k in ap_conn))
				wifi.connect( ssid=ap_conn['ssid'],
					key=ap_conn['key'] or None, bssid=ap_conn.get('mac') or None )
		elif ap_conn: ap_conn, ap_reconn = None, ap_conn
		if ap_conn: st, delay = 'connecting', ap_conn['scan_interval']
		elif ap_reconn or st: # can also be connection from earlier script-run
			st, delay = 'connected', (ap_reconn or ap_base)['check_interval']
		else: st, delay = 'searching', ap_base['scan_interval']
		p_log and p_log(f'State = {st}, delay = {delay:.1f}s')
		await asyncio.sleep(delay)

	p_log('BUG - loop break')


class Sen5x:

	class cmd:

		meas_start = b'\x00!'
		meas_start_td_post = 0.05

		meas_stop = b'\x01\x04'
		meas_stop_td_post = 0.16

		data_ready = b'\x02\x02'
		data_ready_bs_rx = 3
		data_ready_td_read = 0.02
		data_ready_parse = staticmethod(lambda rx: rx[1] != 0)

		data_read = b'\x03\xc4'
		data_read_bs_rx = 24
		data_read_td_read = 0.02
		data_read_parse = staticmethod(
			# pm10, pm25, pm40, pm100, rh, t, voc, nox = result
			lambda rx: map(int, struct.unpack('>HHHHhhhh', rx)) )

		status_read = b'\xd2\x06'
		status_read_bs_rx = 6
		status_read_td_read = 0.02
		status_read_parse = staticmethod( lambda rx,_bits=dict(
				warn_fan_speed=21, err_gas=7, err_rht=6, err_laser=5, err_fan=4 ):
			dict() if not (st := struct.unpack('>I', rx)[0])
				else list(k for k, n in _bits.items() if st & (1<<n)) )

		status_read_clear = b'\xd2\x10'
		status_read_clear_bs_rx = 6
		status_read_clear_td_read = 0.02
		status_read_clear_parse = status_read_parse

		reset = b'\xd3\x04'
		reset_td_post = 0.1

	def __init__(self, i2c, addr=0x69):
		self.bus, self.addr, self.cmd_lock = i2c, addr, asyncio.Lock()
		self.cmd_ms_last = self.cmd_ms_wait = 0

	def sen5x_crc8(self, bs, crc=0xff, crc_map=( # poly=0x31 init=0xff xor=0
			b'\x001bS\xc4\xf5\xa6\x97\xb9\x88\xdb\xea}L\x1f.Cr!\x10\x87\xb6\xe5\xd4'
			b'\xfa\xcb\x98\xa9>\x0f\\m\x86\xb7\xe4\xd5Bs \x11?\x0e]l\xfb\xca\x99\xa8'
			b'\xc5\xf4\xa7\x96\x010cR|M\x1e/\xb8\x89\xda\xeb=\x0c_n\xf9\xc8\x9b\xaa'
			b'\x84\xb5\xe6\xd7@q"\x13~O\x1c-\xba\x8b\xd8\xe9\xc7\xf6\xa5\x94\x032aP'
			b'\xbb\x8a\xd9\xe8\x7fN\x1d,\x023`Q\xc6\xf7\xa4\x95\xf8\xc9\x9a\xab<\r^o'
			b'Ap#\x12\x85\xb4\xe7\xd6zK\x18)\xbe\x8f\xdc\xed\xc3\xf2\xa1\x90\x076eT9'
			b'\x08[j\xfd\xcc\x9f\xae\x80\xb1\xe2\xd3Du&\x17\xfc\xcd\x9e\xaf8\tZkEt\''
			b'\x16\x81\xb0\xe3\xd2\xbf\x8e\xdd\xec{J\x19(\x067dU\xc2\xf3\xa0\x91Gv'
			b'%\x14\x83\xb2\xe1\xd0\xfe\xcf\x9c\xad:\x0bXi\x045fW\xc0\xf1\xa2\x93'
			b'\xbd\x8c\xdf\xeeyH\x1b*\xc1\xf0\xa3\x92\x054gVxI\x1a+\xbc\x8d\xde\xef'
			b'\x82\xb3\xe0\xd1Fw$\x15;\nYh\xff\xce\x9d\xac' )):
		for b in bs: crc = crc_map[crc ^ b]
		return crc

	async def run(self, cmd):
		await self.cmd_lock.acquire()
		try: await self._run(cmd)
		finally: self.cmd_lock.release()
	async def _run(self, cmd, rx=bytearray(24)):
		# Will raise OSError from any I2C interactions
		if self.cmd_ms_last:
			td = time.ticks_diff(time.ticks_ms(), self.cmd_ms_last)
			if (ms := self.cmd_ts_wait - td) > 0: await asyncio.sleep_ms(ms)
			self.cmd_ms_last = 0

		self.bus.writeto(self.addr, getattr(self.cmd, cmd))
		if td := getattr(self.cmd, f'{cmd}_td_read', 0):
			await asyncio.sleep(td)
		if bs := getattr(self.cmd, f'{cmd}_bs_rx', 0):
			self.bus.readfrom_into(self._addr, memoryview(rx)[:bs])

		if td := getattr(self.cmd, f'{cmd}_td_post', 0):
			# Delay is only needed if commands closely follow each other
			self.cmd_ms_last, self.cmd_ts_wait = time.ticks_ms(), int(td * 1000)

		if not bs: return

		for n in range(bs):
			if n % 3 == 2:
				if self.sen5x_crc8(rx[n-2:n]) != rx[n]:
					raise ValueError('RX buffer CRC8 mismatch')
			else: rx[n-(n+1)//3] = rx[n] # compacts bytes in the same buffer
		res = rx[:1+n-(n+1)//3]
		if parse := getattr(self.cmd, f'{cmd}_parse', None): res = parse(res)
		return res


async def sen5x_logger(sen5x, reset=False, verbose=False):
	p_log = verbose and (lambda *a: print('[sensor]', *a))
	if reset: sen5x.run('reset')
	sen5x.run('meas_start')
	p_log and p_log('Started measurement mode')
	try:

		for i in range(10):
			while not sen5x.run('data_ready'):
				p_log and p_log('data_ready delay')
				time.sleep(1.1)

			pm10, pm25, pm40, pm100, rh, t, voc, nox = sen5x.run('data_read')
			p_log and p_log('data:', pm10, pm25, pm40, pm100, rh, t, voc, nox)

			# XXX: check how to convert these values
			# mass_concentration = values.mass_concentration_2p5.physical
			# ambient_temperature = values.ambient_temperature.degrees_celsius

		# XXX: check for these error-flags with a separate interval
		if errs := sen5x.status_read_clear():
			p_err('SEN5x problems detected:', ' '.join(errs))

	finally:
		try: sen5x.run('meas_stop')
		except Exception as err: # avoid hiding original exception, if any
			p_err(f'Failed to stop measurement mode: {err_fmt(err)}')
	p_log and p_log('Stopped measurement mode')


async def main():
	print('--- AQM start ---')
	conf = conf_parse('config.ini')
	tasks = list()

	if conf.wifi_ap_map:
		if not getattr(network, 'WLAN', None):
			p_err('No networking/wifi support detected in micropython firmware, aboring')
			p_err('Either remove/clear [wifi] config section or replace device/firmware')
			return 1
		tasks.append(asyncio.create_task(
			wifi_client(conf.wifi_ap_base, conf.wifi_ap_map) ))

	i2c = dict()
	if conf.sensor_i2c_freq: i2c['freq'] = conf.sensor_i2c_freq
	if conf.sensor_i2c_timeout: i2c['timeout'] = int(conf.sensor_i2c_timeout * 1e3)
	i2c = machine.I2C( conf.sensor_i2c_n,
		sda=machine.Pin(conf.sensor_i2c_pin_sda),
		scl=machine.Pin(conf.sensor_i2c_pin_scl), **i2c )
	sen5x = Sen5x(i2c, conf.sensor_i2c_addr)

	tasks.append(asyncio.create_task(sen5x_logger( sen5x,
		reset=conf.sensor_reset_on_start, verbose=conf.sensor_verbose )))

	try: await asyncio.gather(*tasks)
	finally: print('--- AQM stop ---')

asyncio.run(main())
