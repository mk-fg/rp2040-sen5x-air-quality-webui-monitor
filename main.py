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
	sensor_stop_on_exit = True
	sensor_error_check_interval = 3701.0
	sensor_i2c_n = -1
	sensor_i2c_pin_sda = -1
	sensor_i2c_pin_scl = -1
	sensor_i2c_addr = 105
	sensor_i2c_freq = 100_000 # 0 = machine.I2C default, sen5x has 100kbps max
	sensor_i2c_timeout = 0.0 # 0 = machine.I2C default
	sensor_i2c_error_limit = '8 / 3m'

	webui_sample_interval = 60.0
	webui_sample_count = 1_000

p_err = lambda *a: print('ERROR:', *a) or 1
err_fmt = lambda err: f'[{err.__class__.__name__}] {err}'

def token_bucket_iter(spec): # spec = N / M[smhd], e.g. 10 / 15m
	burst, span = map(str.strip, spec.split('/', 1))
	span = float(span[:-1]) * {'s': 1, 'm': 60, 'h': 3600, 'd': 24*3600}[span[-1]]
	rate = 1 / (1000 * span / (burst := int(burst))) # token / ms
	tokens, ts = max(0, burst - 1), time.ticks_ms()
	while (yield tokens >= 0) or (ts_sync := ts):
		tokens = min( burst, tokens +
			time.ticks_diff(ts := time.ticks_ms(), ts_sync) * rate ) - 1


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

	for sk in 'sensor', 'webui':
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
	p_err('BUG - wifi loop broken')


class Sen5x:

	class Sen5xError(Exception): pass

	# Returns a list of warn/error strings to print, if any
	errs_parse = staticmethod(_errs := lambda rx,_bits=dict(
			warn_fan_speed=21, err_gas=7, err_rht=6, err_laser=5, err_fan=4 ):
		dict() if not (st := struct.unpack('>I', rx)[0])
			else list(k for k, n in _bits.items() if st & (1<<n)) )
	errs_bs = 4

	# pm10, pm25, pm40, pm100, rh, t, voc, nox = values
	# pmX values are in µg/m³, rh = %, t = °C, voc/nox = index
	sample_parse = staticmethod(_sample := lambda rx,
			_ks=(10, 10, 10, 10, 100, 200, 10, 10),
			_nx=(0xffff, 0xffff, 0xffff, 0xffff, 0x7fff, 0x7fff, 0x7fff, 0x7fff):
		list( (v / k if v != nx else None) for v, k, nx in
			zip(struct.unpack('>HHHHhhhh', rx), _ks, _nx) ) )
	sample_bs = 16 # i2c crc8 checksums are already stripped here

	cmd_map = dict(
		# cmd=(tx_cmd, delay) or (tx_cmd, delay, rx_bytes, rx_parser)
		meas_start=(b'\x00!', 0.05),
		meas_stop = (b'\x01\x04', 0.16),
		reset = (b'\xd3\x04', 0.1),
		data_ready = (b'\x02\x02', 0.02, 3, lambda rx: rx[1] != 0),
		data_read = (b'\x03\xc4', 0.02, sample_bs + sample_bs // 2, _sample),
		errs_read = (b'\xd2\x06', 0.02, errs_bs + errs_bs // 2, _errs),
		errs_read_clear = (b'\xd2\x10', 0.02, errs_bs + errs_bs // 2, _errs),
		get_name = (b'\xd0\x14', 0.02, 48, lambda rx: rx.rstrip(b'\0').decode()) )

	crc_map = ( # precalculated for poly=0x31 init=0xff xor=0
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
		b'\x82\xb3\xe0\xd1Fw$\x15;\nYh\xff\xce\x9d\xac' )

	def __init__(self, i2c, addr=0x69):
		self.bus, self.addr, self.cmd_lock = i2c, addr, asyncio.Lock()
		self.rx_mv, self.rx_buff = memoryview(rx := bytearray(24)), rx
		self.cmd_ms_last = self.cmd_ms_wait = 0

	async def __call__(self, cmd_name, parse=True, buff=None):
		if len(cmd := self.cmd_map[cmd_name]) == 2:
			cmd, delay = cmd; rx_bytes = rx_parser = 0
		else:
			cmd, delay, rx_bytes, rx_parser = cmd
			if not parse: rx_parser = None
		# print('i2c [cmd]', cmd_name, cmd, delay, rx_bytes, rx_parser)
		await self.cmd_lock.acquire()
		try: return await self._run(cmd, delay, rx_bytes, rx_parser, buff)
		except OSError as err: raise self.Sen5xError(f'I2C I/O failure: {err_fmt(err)}')
		finally: self.cmd_lock.release()

	async def _run(self, cmd, delay, rx_bytes, rx_parser, rx_smv, crc_map=crc_map):
		if rx_bytes:
			rx = self.rx_mv
			if (n := rx_bytes - len(rx)) > 0:
				self.rx_buff.extend(bytearray(n))
				rx = self.rx_mv = memoryview(self.rx_buff)
			elif len(rx) != rx_bytes: rx = rx[:rx_bytes]

		if self.cmd_ms_last: # delay from last command, if any needed
			td = time.ticks_diff(time.ticks_ms(), self.cmd_ms_last)
			if (ms := self.cmd_ts_wait - td) > 0: await asyncio.sleep_ms(ms)
			self.cmd_ms_last = 0
		# print('i2c [ >>]', [self.addr, cmd])
		self.bus.writeto(self.addr, cmd)

		if rx_bytes:
			if delay: await asyncio.sleep(delay)
			self.bus.readfrom_into(self.addr, rx)
			# print('i2c [<< ]', [self.addr, bytes(rx)])
			for n in range(0, rx_bytes, 3):
				b1, b2, crc = rx[n:n+3]
				if crc != crc_map[b2 ^ crc_map[b1 ^ 0xff]]:
					raise self.Sen5xError('RX buffer CRC8 mismatch')
				if m := n - (n+1) // 3: rx[m], rx[m+1] = b1, b2
			if rx_smv: rx_smv[:] = rx[:rx_bytes-(rx_bytes+1)//3]
			if rx_parser: return rx_parser(rx[:rx_bytes-(rx_bytes+1)//3])

		elif delay: # only needed if commands closely follow each other
			self.cmd_ms_last, self.cmd_ts_wait = time.ticks_ms(), int(delay * 1000)


async def sen5x_poller(
		sen5x, smv, td_data, td_errs, err_rate_limit,
		reset=False, stop=False, verbose=False ):
	p_log = verbose and (lambda *a: print('[sensor]', *a))
	if reset: await sen5x('reset')
	await sen5x('meas_start')
	p_log and p_log('Started measurement mode')
	try:
		err_last = ValueError('Invalid error rate-limiter settings')
		while next(err_rate_limit):
			try: await _sen5x_poller(sen5x, smv, td_data, td_errs, p_log)
			except Sen5x.Sen5xError as err:
				p_log and p_log(f'Sen5x poller failure: {err_fmt(err)}')
				err_last = err
		p_err(f'Sensor-poll failure rate-limiting: {err_fmt(err_last)}')
	finally:
		if stop:
			try: await sen5x('meas_stop')
			except Exception as err: # avoid hiding original exception, if any
				p_err(f'Failed to stop measurement mode: {err_fmt(err)}')
			p_log and p_log('Stopped measurement mode')

async def _sen5x_poller(sen5x, smv, td_data, td_errs, p_log):
	ts_data = ts_errs = -1
	(sn,), sp_offset = struct.unpack_from('>H', smv, 0), 2 + sen5x.errs_bs
	sn_max = (len(smv) - sp_offset) // (sz := sen5x.sample_bs)
	while True:
		ts = time.ticks_ms()

		if ts_data < 0 or (td1 := int(td_data - time.ticks_diff(ts, ts_data))) < 0:
			while (ts_data < 0 or td_data <= 1000) and not await sen5x('data_ready'):
				p_log and p_log('data_ready delay')
				await asyncio.sleep_ms(200)

			sp = sp_offset + sn * sz
			data = await sen5x('data_read', parse=p_log, buff=smv[sp:sp+sz])
			struct.pack_into('>H', smv, 0, sn := (sn + 1) % sn_max)

			if p_log:
				pm10, pm25, pm40, pm100, rh, t, voc, nox = data
				p_log(f'data: {pm10=} {pm25=} {pm40=} {pm100=} {rh=} {t=} {voc=} {nox=}')
			td1, ts_data = td_data, ts

		if ts_errs < 0 or (td2 := int(td_errs - time.ticks_diff(ts, ts_errs))) < 0:
			if errs := await sen5x('errs_read_clear', buff=smv[2:2+sen5x.errs_bs]):
				p_err('SEN5x problems detected:', ' '.join(errs))
			td2, ts_errs = td_errs, ts

		td = min(td1, td2)
		p_log and p_log(f'Delay until next sample/check: {td / 1000:.1f}s')
		await asyncio.sleep_ms(td)
	p_err('BUG - sen5x poller loop broken')


async def main():
	print('--- AQM start ---')
	tasks, conf = list(), conf_parse('config.ini')

	if conf.webui_sample_count >= 2**16: # 1 MiB ought to be enough for everybody
		return p_err('Sample count values >65536 are not supported')
	samples = bytearray( 2 + Sen5x.errs_bs
		+ Sen5x.sample_bs * conf.webui_sample_count )

	if conf.wifi_ap_map:
		if not getattr(network, 'WLAN', None):
			p_err('No networking/wifi support detected in micropython firmware, aboring')
			return p_err('Either remove/clear [wifi] config section or replace device/firmware')
		tasks.append(asyncio.create_task(
			wifi_client(conf.wifi_ap_base, conf.wifi_ap_map) ))

	i2c = dict()
	if conf.sensor_i2c_freq: i2c['freq'] = conf.sensor_i2c_freq
	if conf.sensor_i2c_timeout: i2c['timeout'] = int(conf.sensor_i2c_timeout * 1000)
	if min(conf.sensor_i2c_n, conf.sensor_i2c_pin_sda, conf.sensor_i2c_pin_scl) < 0:
		return p_err('Sensor I2C bus/pin parameters must be set in the config file')
	i2c = machine.I2C( conf.sensor_i2c_n,
		sda=machine.Pin(conf.sensor_i2c_pin_sda),
		scl=machine.Pin(conf.sensor_i2c_pin_scl), **i2c )
	sen5x = Sen5x(i2c, conf.sensor_i2c_addr)

	tasks.append(asyncio.create_task(sen5x_poller(
		sen5x, memoryview(samples),
		td_data=int(conf.webui_sample_interval * 1000),
		td_errs=int(conf.sensor_error_check_interval * 1000),
		err_rate_limit=token_bucket_iter(conf.sensor_i2c_error_limit),
		stop=conf.sensor_stop_on_exit,
		reset=conf.sensor_reset_on_start,
		verbose=conf.sensor_verbose )))

	# XXX: webui server task/component

	try: await asyncio.gather(*tasks)
	finally: print('--- AQM stop ---')

asyncio.run(main())
