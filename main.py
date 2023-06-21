import struct, machine, time

try: import network # required for wifi stuff
except ImportError: network = None
try: import socket # required for webui
except ImportError: socket = None

try: import uasyncio as asyncio
except ImportError: import asyncio # newer mpy naming


class AQMConf:

	wifi_ap_base = dict(
		scan_interval=20.0, check_interval=10.0 )
	wifi_ap_map = dict()

	sensor_verbose = False
	sensor_sample_interval = 60.0
	sensor_sample_count = 1_000
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

	webui_verbose = False
	webui_port = 80
	webui_conn_backlog = 5

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
				p_log and p_log(f'Scan results [ {" // ".join(sorted(ssid_set))} ]')
				for ssid, ap in ap_map.items():
					if ssid in ssid_set:
						ap_conn = dict(ap_base, **ap)
						break
			if ap_conn:
				p_log and p_log(f'Connecting to [ {ap_conn["ssid"]} ]')
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
	raise RuntimeError('BUG - wifi loop stopped unexpectedly')


class Sen5x:

	class Sen5xError(Exception): pass

	# Returns a list of warn/error strings to print, if any
	errs_parse = staticmethod(_errs := lambda rx,_bits=dict(
			warn_fan_speed=21, err_gas=7, err_rht=6, err_laser=5, err_fan=4 ):
		tuple() if not (st := struct.unpack('>I', rx)[0])
			else tuple(k for k, n in _bits.items() if st & (1<<n)) )
	errs_bs = 4

	# pm10, pm25, pm40, pm100, rh, t, voc, nox = values
	# pmX values are in µg/m³, rh = %, t = °C, voc/nox = index
	sample_parse = staticmethod(_sample := lambda rx,
			_ks=(10, 10, 10, 10, 100, 200, 10, 10),
			_nx=(0xffff, 0xffff, 0xffff, 0xffff, 0x7fff, 0x7fff, 0x7fff, 0x7fff):
		tuple( (v / k if v != nx else None) for v, k, nx in
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
		sen5x, srb, td_data, td_errs, err_rate_limit,
		reset=False, stop=False, verbose=False ):
	p_log = verbose and (lambda *a: print('[sensor]', *a))
	if reset: await sen5x('reset')
	await sen5x('meas_start')
	p_log and p_log('Started measurement mode')
	try:
		err_last = ValueError('Invalid error rate-limiter settings')
		while next(err_rate_limit):
			try: await _sen5x_poller(sen5x, srb, td_data, td_errs, p_log)
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

async def _sen5x_poller(sen5x, srb, td_data, td_errs, p_log):
	errs_seen = set()
	ts_data = ts_errs = -1 # time of last data/errs poll
	while True:
		ts = ts_loop = time.ticks_ms()

		if ts_data < 0 or (td1 := td_data - time.ticks_diff(ts, ts_data)) < 0:
			if ts_data < 0 or td_data <= 1000:
				while not await sen5x('data_ready'):
					p_log and p_log('data_ready delay')
					await asyncio.sleep_ms(200)
				ts = time.ticks_ms()
			buff = srb.sample_mv(ts)
			data = await sen5x('data_read', parse=p_log, buff=buff)
			srb.sample_mv_commit(ts)
			if p_log:
				pm10, pm25, pm40, pm100, rh, t, voc, nox = data
				p_log(f'data: {pm10=} {pm25=} {pm40=} {pm100=} {rh=} {t=} {voc=} {nox=}')
			if time.ticks_diff(ts := time.ticks_ms(), ts_data) - td_data > td_data:
				td1, ts_data = td_data, ts # set new ts-base at the start or after skips
			else: # next poll is ts_loop + td_data, to keep intervals from drifting
				ts_data = ts_loop
				td1 = td_data - time.ticks_diff(ts, ts_data)

		if ts_errs < 0 or (td2 := td_errs - time.ticks_diff(ts, ts_errs)) < 0:
			# Errors are logged once here, but stick in register/webui until reset/reboot
			errs = await sen5x('errs_read', buff=srb.buff_mv_err)
			if errs_new := set(errs).difference(errs_seen):
				p_err('New SEN5x problems detected:', ' '.join(errs_new))
				errs_seen.update(errs_new)
			td2, ts_errs = td_errs, ts

		td = min(td1, td2)
		p_log and p_log(f'Delay until next sample/check: {td / 1000:.1f}s')
		await asyncio.sleep_ms(td)
	raise RuntimeError('BUG - sen5x poller loop stopped unexpectedly')


class SampleRingBuffer:
	# Samples are stored in bytearray as they're received in Sen5x (circa crc's)
	# n points to current free slot, n_ts is ticks_ms of the last slot
	# If new sample has ts - n_ts > 2 * n_td,
	#   blk_skip is inserted with extra ms to add on top of n_td for that slot,
	#   otherwise delta between samples is always n_td, as enforced by poller.
	# To read samples back, blocks can be iterated in (n:n0] with reverse order,
	#   decrementing timestamp by regular delta and decoded blk_skip values, if any.

	blk_skip = b'\xff\xfe\0\0' # two first impossible-values to mark time-skip blocks

	def __init__(self, td_ms, count):
		self.n = self.n_loops = self.n_skips = 0
		self.n_ts = self.skip_last_pos = None
		self.n_td, self.n_max = td_ms, count
		self.buff = bytearray(Sen5x.errs_bs + Sen5x.sample_bs * self.n_max)
		self.buff_mv = memoryview(self.buff)
		self.buff_mv_err = self.buff_mv[:Sen5x.errs_bs]

	def sample_mv( self, ts,
			_bs=Sen5x.sample_bs, _pos0=Sen5x.errs_bs, _blk_skip=blk_skip ):
		# Returns memoryview to store new sample into
		pos = _pos0 + self.n * _bs
		if self.buff[pos:pos+4] == _blk_skip: self.n_skips -= 1
		if self.n_ts is not None and (
				td := time.ticks_diff(ts, self.n_ts) - self.n_td ) > self.n_td:
			self.sample_mv_commit(ts, td)
			return self.sample_mv(ts + self.n_td)
		return self.buff_mv[pos:pos+_bs]

	def sample_mv_commit( self, ts, td_skip=None,
			_bs=Sen5x.sample_bs, _pos0=Sen5x.errs_bs, _blk_skip=blk_skip ):
		# Mark current/last returned sample_mv as used
		if td_skip: # skip block, storing skipped time-delta in it
			if pos := self.skip_last_pos: # collapse repeated blk_skip, if any
				td_skip += self.n_td + int.from_bytes(self.buff[pos+4:pos+8], 'big')
				self.n -= 1
			else:
				pos = self.skip_last_pos = _pos0 + self.n * _bs
				self.buff[pos:pos+4] = _blk_skip
				self.n_skips += 1
			if td_skip > 0xffffffff: # >50d delta = overflow - flush all old data
				self.n_ts = None; self.n = self.n_loops = self.n_skips = 0; return
			self.buff[pos+4:pos+8] = td_skip.to_bytes(4, 'big')
		else: self.skip_last_pos = None
		self.n_ts, self.n = ts, (self.n + 1) % self.n_max
		if not self.n: self.n_loops += 1

	def data_chunks(self, _bs=Sen5x.sample_bs, _pos0=Sen5x.errs_bs):
		if not self.n: return [self.buff_mv[_pos0:]] if self.n_loops else []
		n = _pos0 + self.n * _bs
		return ( [self.buff_mv[_pos0:n]]
			if not self.n_loops else [self.buff_mv[n:], self.buff_mv[_pos0:n]] )

	def data_samples_count(self):
		return (self.n_max if self.n_loops else self.n) - self.n_skips

	def data_samples_raw( self,
			_bs=Sen5x.sample_bs, _pos0=Sen5x.errs_bs, _blk_skip=blk_skip ):
		# Yields (offset_ms, sample_bytes) tuples in reverse-chronological order.
		# Time offsets are positive integers (from now into past), and can be irregular.
		# First returned sample (latest one chronologically) will have offset=0ms.
		td, chunks = 0, self.data_chunks()
		for chunk in reversed(chunks):
			pos = len(chunk)
			while (pos := pos - _bs) >= 0:
				if chunk[pos:pos+4] != _blk_skip:
					yield (td, bytes(chunk[pos:pos+_bs]))
					td += self.n_td
				else: td += int.from_bytes(chunk[pos+4:pos+8], 'big')

	def data_samples(self, ts_now=0, _parse=Sen5x.sample_parse):
		# Yields (ts, sample) values, with ts = approx posix timestamp in seconds,
		#   and sample is (pm10, pm25, pm40, pm100, rh, t, voc, nox) tuple of values,
		#   in reverse-chronological order (latest sample first).
		# Values are either float, or None if sensor returns N/A value
		#   (not ready yet, not supported by this model, broken hardware, etc).
		for td_ms, sample_bs in self.data_samples_raw():
			yield (ts_now - (td_ms / 1000), _parse(sample_bs))


class WebUI:

	class Req:
		def __init__(self, **kws): self.update(**kws)
		def update(self, **kws):
			for k,v in kws.items(): setattr(self, k, v)

	def __init__(self, srb, verbose=False):
		self.srb, self.verbose, self.req_n = srb, verbose, 0

	async def run_server(self, server):
		await server.wait_closed()
		raise RuntimeError('BUG - httpd server stopped unexpectedly')

	async def request(self, sin, sout):
		self.req_n += 1
		req = self.Req(sin=sin, sout=sout, log=self.verbose and (
			lambda *a,_pre=f'[http.{self.req_n:03d}]': print(_pre, *a) ))
		req.log and req.log('Peer:', req.sin.get_extra_info('peername'))
		line = (await sin.readline()).strip()
		try: req.verb, req.url, req.proto = line.split(None, 2)
		except ValueError: return req.log and req.log('Req non-http line:', line)
		req.log and req.log(f'Request: {req.verb.decode()} {req.url.decode()}')
		while (await req.sin.readline()).strip(): pass # flush headers, if any
		req.sin.close()
		return await self.req_handler(req)

	async def res_err(self, req, code, msg=''):
		req.log and req.log(f'Response: http-{code} [{msg or "-"}]')
		req.sout.write(f'HTTP/1.0 {code} {msg}\r\n'.encode())
		body = ( f'HTTP Error [{code}]: {msg}\n'
			if msg else f'HTTP Error [{code}]\n' ).encode()
		req.sout.write(b'Server: aqm\r\nContent-Type: text/plain\r\n')
		req.sout.write(f'Content-Length: {len(body)}\r\n\r\n'.encode())
		req.sout.write(body); await req.sout.drain(); req.sout.close()

	async def req_handler(self, req):
		# TODO: add /favicon.ico
		req.url_map = dict(
			page_index=(b'/', b'/index.html', b'/index.htm'),
			data_csv=(b'/data/all/latest-first/samples.csv',),
			data_bin=(b'/data/all/latest-first/samples.8Bms_16Bsen5x_tuples.bin',) )
		req.verb = req.verb.lower()
		if req.verb != b'get':
			return await self.res_err(req, 405, 'Method Not Allowed')
		while b'//' in req.url: req.url = req.url.replace(b'//', b'/')
		for k, k_url in req.url_map.items():
			if req.url not in k_url: continue
			await getattr(self, f'req_{k}')(req)
			break
		else: return await self.res_err(req, 404, 'Not Found')
		await req.sout.drain(); req.sout.close()

	async def req_page_index(self, req):
		# XXX: add sensor errors here
		req.sout.write( b'HTTP/1.0 200 OK\r\n'
			b'Server: aqm\r\nContent-Type: text/html\r\n' )
		page = b'''<!DOCTYPE html>
			<meta charset='utf-8'><title>{title}</title><body>
			<h3>{title}</h3>
			<ul>
				<li><a href='{url_data_csv}'>Data export in CSV</a>
				<li><a href='{url_data_bin}'>Data export in binary format</a>
					[ 8B time-offset ms (0 = latest) || 16B SEN5x sample ]*
			</ul>
		'''.replace(b'\n\t\t\t', b'\n').replace(b'\t', b'  ').format(
			title='RP2040 SEN5x Air Quality Monitor',
			**dict((f'url_{k}', url[0].decode()) for k, url in req.url_map.items()) )
		req.sout.write(f'Content-Length: {len(page)}\r\n\r\n'.encode())
		req.sout.write(page)

	async def req_data_bin(self, req):
		req.sout.write( b'HTTP/1.0 200 OK\r\n'
			b'Server: aqm\r\nContent-Type: application/octet-stream\r\n'
			b'X-Format: [ 8B time-offset ms (0 = latest) || 16B SEN5x sample ]*\r\n' )
		bs = self.srb.data_samples_count() * (4 + 16)
		req.sout.write(f'Content-Length: {bs}\r\n\r\n'.encode())
		for td, sample in self.srb.data_samples_raw():
			# time-offset ms can overflow here, but should be very unlikely (~50d)
			req.sout.write(struct.pack('>I16s', td & 0xffffffff, sample))

	async def req_data_csv(self, req):
		req.sout.write( b'HTTP/1.0 200 OK\r\n'
			b'Server: aqm\r\nContent-Type: text/csv\r\n' )
		header = b'time_offset, pm10, pm25, pm40, pm100, rh, t, voc, nox\n'
		line = bytearray( b' 123456.0, 123.0, 123.0,'
			b' 123.0, 123.0, 12.34, 12.345, 1234.0, 1234.0\n' )
		bs = len(header) + self.srb.data_samples_count() * len(line)
		req.sout.write(f'Content-Length: {bs}\r\n\r\n'.encode())
		req.sout.write(header)
		# for f in line.rstrip().split(b','): fields.append((n, m:=len(f))); n+=m+1
		fields = (0,9),(10,6),(17,6),(24,6),(31,6),(38,6),(45,7),(53,7),(61,7)
		fmt = dict((vlen, f'{{:>{vlen}}}') for pos,vlen in fields)
		for ts, sample in self.srb.data_samples():
			vals = (abs(ts),) + sample
			for v, (pos, vlen) in zip(vals, fields):
				if v is None: vs = b''
				else:
					vs = str(float(v))[:vlen]
					if '.' not in vs:
						k = header.decode().split(',')[vals.index(v)]
						raise ValueError( 'Sensor value too long'
							+ f' for CSV field [{k.strip()}:{vlen}]: {v}' )
					vs = vs.rstrip('.').encode()
				line[pos:pos+vlen] = fmt[vlen].format(vs).encode()
			req.sout.write(line)


async def main():
	print('--- AQM start ---')
	conf, components = conf_parse('config.ini'), list()

	if conf.sensor_sample_count >= 2**16: # 1 MiB ought to be enough for everybody
		return p_err('Sample count values >65536 are not supported')
	conf.sensor_sample_interval = int(conf.sensor_sample_interval * 1000)
	srb = SampleRingBuffer(
		conf.sensor_sample_interval, conf.sensor_sample_count )

	if conf.wifi_ap_map:
		if not getattr(network, 'WLAN', None):
			p_err('No networking/wifi support detected in micropython firmware, aboring')
			return p_err('Either remove/clear [wifi] config section or replace device/firmware')
		components.append(wifi_client(conf.wifi_ap_base, conf.wifi_ap_map))

	i2c = dict()
	if conf.sensor_i2c_freq: i2c['freq'] = conf.sensor_i2c_freq
	if conf.sensor_i2c_timeout: i2c['timeout'] = int(conf.sensor_i2c_timeout * 1000)
	if min(conf.sensor_i2c_n, conf.sensor_i2c_pin_sda, conf.sensor_i2c_pin_scl) < 0:
		return p_err('Sensor I2C bus/pin parameters must be set in the config file')
	i2c = machine.I2C( conf.sensor_i2c_n,
		sda=machine.Pin(conf.sensor_i2c_pin_sda),
		scl=machine.Pin(conf.sensor_i2c_pin_scl), **i2c )
	sen5x = Sen5x(i2c, conf.sensor_i2c_addr)
	components.append(sen5x_poller(
		sen5x, srb, td_data=conf.sensor_sample_interval,
		td_errs=int(conf.sensor_error_check_interval * 1000),
		err_rate_limit=token_bucket_iter(conf.sensor_i2c_error_limit),
		stop=conf.sensor_stop_on_exit,
		reset=conf.sensor_reset_on_start,
		verbose=conf.sensor_verbose ))

	if socket:
		webui = WebUI(srb, verbose=conf.webui_verbose)
		httpd = await asyncio.start_server( webui.request,
			'0.0.0.0', conf.webui_port, backlog=conf.webui_conn_backlog )
		components.append(webui.run_server(httpd))
	else: p_err('Socket API not supported in micropython firmware, not starting WebUI')

	try: await asyncio.gather(*components)
	finally: print('--- AQM stop ---')

asyncio.run(main())
