import os, gc, struct, machine, time

try: import network # required for wifi stuff
except ImportError: network = None
try: import socket # required for webui
except ImportError: socket = None

try: import uasyncio as asyncio
except ImportError: import asyncio # newer mpy naming


class AQMConf:

	wifi_sta_conf = dict(scan_interval=20.0, check_interval=10.0)
	wifi_sta_aps = dict()
	wifi_ap_conf = dict()

	sensor_verbose = False
	sensor_sample_interval = 60.0
	sensor_sample_count = 1_000
	sensor_reset_on_start = False
	sensor_stop_on_exit = True
	sensor_error_check_interval = 3701.0
	sensor_fan_clean_min_interval = 24 * 3600.0
	sensor_i2c_n = -1
	sensor_i2c_pin_sda = -1
	sensor_i2c_pin_scl = -1
	sensor_i2c_addr = 105
	sensor_i2c_freq = 100_000 # 0 = machine.I2C default, sen5x has 100kbps max
	sensor_i2c_timeout = 0.0 # 0 = machine.I2C default
	sensor_i2c_error_limit = '8 / 3m' # abort on >8 errs in 3m(ins) (or s/m/h/d units)
	sensor_temp_comp_offset = 0.0
	sensor_temp_comp_slope = 0.0
	sensor_temp_comp_time_const = 0

	webui_verbose = False
	webui_port = 80
	webui_conn_backlog = 5
	webui_title = 'RP2040 SEN5x Air Quality Monitor'
	webui_url_prefix = ''
	webui_marks_storage_bytes = 512
	webui_d3_api = 7
	webui_d3_load_from_internet = False

	alerts_verbose = False
	alerts_nx = -999.0
	alerts_max_pm = alerts_min_t = alerts_max_t = alerts_nx
	alerts_min_rh = alerts_max_rh = alerts_max_voc = alerts_max_nox = alerts_nx
	alerts_send_to = ''
	alerts_bind_port = 5683

p_err = lambda *a: print('ERROR:', *a)
err_fmt = lambda err: f'[{err.__class__.__name__}] {err}'

def token_bucket_iter(spec): # spec = N / M[smhd], e.g. 10 / 15m
	burst, span = map(str.strip, spec.split('/', 1))
	span = float(span[:-1]) * {'s': 1, 'm': 60, 'h': 3600, 'd': 24*3600}[span[-1]]
	rate = 1 / (1000 * span / (burst := int(burst))) # token / ms
	tokens, ts = max(0, burst - 1), time.ticks_ms()
	while (yield tokens >= 0) or (ts_sync := ts):
		tokens = min( burst, tokens +
			time.ticks_diff(ts := time.ticks_ms(), ts_sync) * rate ) - 1

def val_iter(val=None): # placeholder for iterators
	while True: yield val

# XXX: more mobile-friendly/responsive WebUI
# webui_head is not templated, so can be full of {}
webui_head = b'''<!DOCTYPE html>
<head><meta charset=utf-8><style>
:root { --c-fg: #d2f3ff; --c-bg: #09373b; }
body { margin: 0 auto; padding: 1em;
	max-width: 960px; color: var(--c-fg); background: var(--c-bg); }
h3, ul { margin-block-end: 0; }
a, a:visited { color: #5dcef5; }
svg g { color: #d2f3ff; }
svg text { font: 1rem 'Liberation Sans', 'Luxi Sans', sans-serif; }
svg .axis { opacity: 0.5; } .axis.fg { opacity: 1; } .axis text { fill: currentColor; }
svg .grid line { stroke: #275259; } .grid .domain { stroke: none; }
svg .line { fill: none; } .overlay { fill: none; pointer-events: all; }
svg .focus line { fill: none; stroke: #81b0da; }
svg .focus tspan { paint-order: stroke; stroke: #0008; stroke-width: .7rem; }
svg .focus tspan.hl { stroke: #025fb3; }
svg .marks line { stroke-width: 2; }
#exports { float: left; } #actions { float: right; }
#errors, #graph, #marks { clear: both; }
#errors { width: 40rem; list-style: none; padding: 0; }
#errors li { background: #9b2220; font-weight: bold;
	margin: .5rem; padding: .5rem 1rem; border-radius: .4rem; }
#errors li::before { content: '⚠️'; margin-right: .4rem; }
#marks {
	display: flex; align-items: stretch; position: relative;
	min-height: 10rem; width: 90%; margin: 1rem auto; }
#marks.hide { display: none; }
#marks button {
	position: absolute; top: .4rem; right: 1rem;
	border: var(--c-fg) outset 1px; border-radius: .5rem;
	padding: .4rem 1rem; cursor: pointer; color: var(--c-fg); background: #5dcef520; }
#marks button:disabled { color: #5dcef580; cursor: not-allowed; }
#marks div, #marks textarea {
	flex-grow: 0; margin: 0; padding: .6rem 0;
	border: var(--c-bg) inset 1px; line-height: 1.5rem;
	font: 1rem 'Liberation Mono', 'Luxi Mono', monospace; }
#marks div { position: relative; min-width: 2rem; white-space: nowrap; text-align: center; }
#marks textarea { flex-grow: 1; color: currentColor;
	padding: .6rem; border-color: var(--c-fg); background: var(--c-bg); }
</style>'''

webui_body = b'''
<title>{title}</title><body><h3>{title}</h3>
<ul id=exports>
	<li><a href={url_data_csv!r}>Data export in CSV</a>
	<li><a id=data-url href={url_data_bin!r}>Data export in binary format</a>
</ul>
<ul id=actions>{sen_actions}</ul>
<ul id=errors>{err_msgs}</ul>
<div id=graph><svg></svg></div>
<div id=marks class=hide>
	<div></div>
	<textarea></textarea>
	<button>Save</button>
</div>
<script>
window.aqm_opts = {{
	d3_api: {d3_api},
	d3_from_cdn: {d3_from_cdn},
	marks_bs_max: {marks_bs_max} }}
window.aqm_urls = {{
	data: {url_data_bin!r},
	marks: {url_data_marks!r},
	d3: {url_js_d3!r} }}
</script>
<script type=text/javascript src={url_js!r}></script>'''

webui_err_msgs = dict(
	warn_fan_speed='Fan - speed out of range',
	err_gas='Gas sensor error (VOC/NOx)',
	err_rht='RHT (temp/humidity) sensor communication error',
	err_laser='Laser failure',
	err_fan='Fan - mechanical failure (blocked/broken)' )


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
	wifi_sec_map = {'wpa2-psk': 3, 'wpa/wpa2-psk': 4, 'wpa-psk': 2}
	wifi_conf_keys = dict(
		country=str, verbose=lambda v: bool_map[v],
		scan_interval=float, check_interval=float, ssid=str, key=str,
		hostname=str, channel=int, reconnects=int, txpower=float,
		mac=lambda v: v.encode(), hidden=lambda v: bool_map[v],
		security=lambda v: wifi_sec_map[v.lower() or 'wpa2-psk'],
		pm=lambda v: network and getattr(network.WLAN, f'PM_{v.upper()}') )

	if sec := conf_lines.get('wifi-ap'):
		ap, prefix = dict(), '[conf.wifi-ap]'
		for key_raw, key, val in sec:
			if not (key_func := wifi_conf_keys.get(key)):
				p_err(f'{prefix} Unrecognized config key [ {key_raw} ]')
				continue
			try: ap[key] = key_func(val)
			except Exception as err:
				p_err(f'{prefix} Failed to process {key_raw}=[ {val} ]: {err_fmt(err)}')
		if ap.get('ssid') and ap.get('key'): conf.wifi_ap_conf = ap

	if sec := conf_lines.get('wifi-client') or conf_lines.get('wifi'):
		ap_map = {None: conf.wifi_sta_conf}
		ssid, ap, ck = None, dict(), 'conf.wifi-client'
		sec.append(('ssid', 'ssid', None)) # close last ssid= section
		for key_raw, key, val in sec:
			if key == 'country': ap_map[None][key] = val
			elif key == 'verbose': ap_map[None][key] = bool_map[val]
			elif key == 'ssid':
				if ssid and not ap:
					p_err(f'{prefix} Skipping ssid without config [ {ssid} ]')
				else:
					if ssid not in ap_map: ap_map[ssid] = ap_map[None].copy()
					ap_map[ssid].update(ap)
					ap.clear()
				ssid = val
			elif key_func := wifi_conf_keys.get(key):
				try: ap[key] = key_func(val)
				except Exception as err:
					p_err(f'{prefix} Failed to process [ {ssid} ] {key_raw}=[ {val} ]: {err_fmt(err)}')
			else: p_err(f'{prefix} Unrecognized config key [ {key_raw} ]')
		conf.wifi_sta_conf, conf.wifi_sta_aps = ap_map.pop(None), ap_map

	for sk in 'sensor', 'webui', 'alerts':
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


def wifi_ap_setup(ap):
	p_log = ap.get('verbose') and (lambda *a: print('[wifi]', *a))
	if cc := ap.get('country'): network.country(cc)
	ap_keys = [ 'ssid', 'key', 'hostname', 'security',
		'pm', 'channel', 'reconnects', 'txpower', 'mac', 'hidden' ]
	wifi = network.WLAN(network.AP_IF)
	wifi.config(**dict((k, ap[k]) for k in ap_keys if k in ap))
	wifi.active(True)
	ip, net, gw, dns = wifi.ifconfig()
	print(f'Setup Access Point [ {ap.get("ssid")} ] with IP {ip} (mask {net})')


async def wifi_client(conf_base, ap_map):
	def ssid_str(ssid):
		try: return ssid.decode() # mpy 1.20 doesn't support errors= handling
		except UnicodeError: return repr(ssid)[2:-1] # ascii + backslash-escapes
	p_log = conf_base.get('verbose') and (lambda *a: print('[wifi]', *a))
	if cc := conf_base.get('country'): network.country(cc)
	wifi = network.WLAN(network.STA_IF)
	wifi.active(True)
	p_log and p_log('Activated')
	ap_conn = ap_reconn = addr_last = None
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
				ssid_map = dict((ssid_str(ap[0]), ap[0]) for ap in wifi.scan())
				p_log and p_log(f'Scan results [ {" // ".join(sorted(ssid_map))} ]')
				for ssid, ap in ap_map.items():
					if ssid_raw := ssid_map.get(ssid):
						ap_conn = dict(conf_base, ssid=ssid_raw, **ap)
						break
			if ap_conn:
				p_log and p_log(f'Connecting to [ {ssid_str(ap_conn["ssid"])} ]')
				wifi.config(**dict((k, ap_conn[k]) for k in ap_keys if k in ap_conn))
				wifi.connect( ssid=ap_conn['ssid'],
					key=ap_conn['key'] or None, bssid=ap_conn.get('mac') or None )
		elif ap_conn: ap_conn, ap_reconn = None, ap_conn
		if ap_conn: st, delay = 'connecting', ap_conn['scan_interval']
		elif ap_reconn or st: # can also be connection from earlier script-run
			st, delay = 'connected', (ap_reconn or conf_base)['check_interval']
		else: st, delay = 'searching', conf_base['scan_interval']
		if addrs := wifi.ifconfig():
			if p_log: st += f' [{addrs[0]}]'
			elif addr_last != addrs[0]:
				print('[wifi] Current IP Address:', addr_last := addrs[0])
		p_log and p_log(f'State = {st}, delay = {delay:.1f}s')
		await asyncio.sleep(delay)
	raise RuntimeError('BUG - wifi loop stopped unexpectedly')


class Sen5x:

	class Sen5xError(Exception): pass

	# Returns a tuple of warn/error strings to print, if any
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
		# cmd=(tx_cmd, delay[, tx_encoder]) or (tx_cmd, delay, rx_bytes, rx_parser)
		meas_start=(b'\x00!', 0.05),
		meas_stop = (b'\x01\x04', 0.16),
		reset = (b'\xd3\x04', 0.1),
		clean_fan = (b'\x56\x07', 0.02),
		temp_offset_get = (b'`\xb2', 0.02),
		temp_offset_set = ( b'`\xb2', 0.02, lambda offset, slope, time_const:
			struct.pack('>hhH', round(offset * 200), round(slope * 10_000), time_const) ),
		data_ready = (b'\x02\x02', 0.02, 3, lambda rx: rx[1] != 0),
		data_read = (b'\x03\xc4', 0.02, sample_bs + sample_bs // 2, _sample),
		errs_read = (b'\xd2\x06', 0.02, errs_bs + errs_bs // 2, _errs),
		errs_read_clear = (b'\xd2\x10', 0.02, errs_bs + errs_bs // 2, _errs),
		get_serial = (b'\xd0\x33', 0.02, 48, lambda rx: rx.rstrip(b'\0').decode()) )

	crc8_map = ( # precalculated for poly=0x31 init=0xff
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
		self.cmd_ms_last = self.cmd_ms_wait = -1

	async def __call__(self, cmd_name, *cmd_args, parse=True, buff=None):
		tx_bytes = rx_bytes = rx_parser = 0
		if len(cmd := self.cmd_map[cmd_name]) == 2: cmd, delay = cmd
		elif len(cmd) == 3:
			cmd, delay, tx_bytes = cmd
			cmd_args, tx_bytes = None, tx_bytes(*cmd_args)
		else:
			cmd, delay, rx_bytes, rx_parser = cmd
			if not parse: rx_parser = None
		if cmd_args: raise ValueError(f'Arguments to no-TX SEN5x command: {cmd_args}')
		await self.cmd_lock.acquire()
		try: return await self._run(cmd, delay, tx_bytes, rx_bytes, rx_parser, buff)
		except OSError as err: raise self.Sen5xError(f'I2C I/O failure: {err_fmt(err)}')
		finally: self.cmd_lock.release()

	async def _run( self, cmd, delay,
			tx_bytes, rx_bytes, rx_parser, rx_smv, crc8_map=crc8_map ):
		if tx_bytes:
			tx = bytearray((n := len(tx_bytes)) + n // 2)
			for n in range(0, n, 2):
				(b1, b2), m = tx_bytes[n:n+2], 3 * n // 2
				tx[m], tx[m+1], tx[m+2] = b1, b2, crc8_map[b2 ^ crc8_map[b1 ^ 0xff]]
			cmd += tx

		if rx_bytes:
			rx = self.rx_mv
			if (n := rx_bytes - len(rx)) > 0:
				self.rx_buff.extend(bytearray(n))
				rx = self.rx_mv = memoryview(self.rx_buff)
			elif len(rx) != rx_bytes: rx = rx[:rx_bytes]

		if self.cmd_ms_last >= 0: # delay from last command, if needed
			td = time.ticks_diff(time.ticks_ms(), self.cmd_ms_last)
			if (ms := self.cmd_ts_wait - td) > 0: await asyncio.sleep_ms(ms)
			self.cmd_ms_last = -1
		self.bus.writeto(self.addr, cmd)

		if rx_bytes:
			if delay: await asyncio.sleep(delay)
			self.bus.readfrom_into(self.addr, rx)
			for n in range(0, rx_bytes, 3):
				b1, b2, crc = rx[n:n+3]
				if crc != crc8_map[b2 ^ crc8_map[b1 ^ 0xff]]:
					raise self.Sen5xError('RX buffer CRC8 mismatch')
				if m := n - (n+1) // 3: rx[m], rx[m+1] = b1, b2
			if rx_smv: rx_smv[:] = rx[:rx_bytes-(rx_bytes+1)//3]
			if rx_parser: return rx_parser(rx[:rx_bytes-(rx_bytes+1)//3])

		elif delay: # only needed if commands closely follow each other
			self.cmd_ms_last, self.cmd_ts_wait = time.ticks_ms(), int(delay * 1000)

	def fan_clean_func_iter(self, td_min):
		ts_wait, clean_func = list(), lambda: ( None if ts_wait
			else (ts_wait.append(time.ticks_ms()), self('clean_fan'))[1] )
		while True:
			if ts_wait:
				if time.ticks_diff(time.ticks_ms(), ts_wait[-1]) < td_min:
					yield; continue
				ts_wait.clear()
			yield clean_func


async def sen5x_poller(
		sen5x, srb, td_data, td_errs, err_rate_limit,
		stop_on_exit=False, alerts=None, verbose=False ):
	p_log = verbose and (lambda *a: print('[sensor]', *a))
	await sen5x('meas_start')
	p_log and p_log('Started measurement mode')
	await asyncio.sleep(1) # avoids unnecessary data_ready checks
	try:
		err_last = ValueError('Invalid error rate-limiter settings')
		while next(err_rate_limit):
			try: await _sen5x_poller(sen5x, srb, alerts, td_data, td_errs, p_log)
			except Sen5x.Sen5xError as err:
				p_log and p_log(f'Sen5x poller failure: {err_fmt(err)}')
				err_last = err
		p_err(f'Sensor-poll failure rate-limiting: {err_fmt(err_last)}')
	finally:
		if stop_on_exit:
			try: await sen5x('meas_stop')
			except Exception as err: # avoid hiding original exception, if any
				p_err(f'Failed to stop measurement mode: {err_fmt(err)}')
			p_log and p_log('Stopped measurement mode')

async def _sen5x_poller(sen5x, srb, alerts, td_data, td_errs, p_log):
	errs_seen, td_slack = set(), 10 # less loops when sleep() wakes up early
	ts_data = ts_errs = -1 # time of last data/errs poll
	while True:
		ts = ts_loop = time.ticks_ms()

		if ts_data < 0 or (td1 := td_data - time.ticks_diff(ts, ts_data)) < td_slack:
			if ts_data < 0 or td_data <= 1500:
				# Data might not be ready if fan auto-cleanup is running,
				#  but null-returns are handled, so it's same missing values.
				while not await sen5x('data_ready'):
					p_log and p_log('data_ready delay')
					await asyncio.sleep_ms(200)
			await srb.lock.acquire()
			try:
				ts, buff = time.ticks_ms(), srb.sample_mv(ts)
				data = await sen5x('data_read', parse=p_log, buff=buff)
				srb.sample_mv_commit(ts)
			finally: srb.lock.release()
			if p_log:
				pm10, pm25, pm40, pm100, rh, t, voc, nox = data
				p_log(f'data: {pm10=} {pm25=} {pm40=} {pm100=} {rh=} {t=} {voc=} {nox=}')
			if alerts: alerts.check(data, bytes(buff))
			if time.ticks_diff(ts := time.ticks_ms(), ts_data) - td_data > td_data:
				td1, ts_data = td_data, ts # set new ts-base at the start or after skips
			else: # next poll at ts_loop + td_data, to keep intervals from drifting
				td1 = td_data - time.ticks_diff(ts, ts_data := ts_loop)

		if ts_errs < 0 or (td2 := td_errs - time.ticks_diff(ts, ts_errs)) < td_slack:
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
	# Samples are stored in bytearray as they're received in Sen5x (crc8s stripped)
	# n is of current free slot, n_ts is ticks_ms of the last slot, n_td = sampling interval
	# If new sample has ts - n_ts > 2 * n_td (i.e. doesn't belong in next slot),
	#   blk_skip is inserted with extra ms to add on top of n_td for that slot,
	#   otherwise delta between samples is always n_td, as enforced by poller.
	# To read samples back, blocks can be iterated in a circular reverse-order,
	#   decrementing timestamp by regular delta + decoded blk_skip values (if any).

	blk_skip = b'\xff\xfe\0\0' # two first impossible-values to mark time-skip blocks
	sbs, ebs, s0 = Sen5x.sample_bs, Sen5x.errs_bs, Sen5x.errs_bs # binary sample params
	s_parse, errs_parse = staticmethod(Sen5x.sample_parse), staticmethod(Sen5x.errs_parse)

	def __init__(self, td_ms, count):
		self.n = self.n_loops = self.n_skips = 0
		self.n_ts = self.skip_last_pos = None
		self.n_td, self.n_max = td_ms, count
		self.buff = bytearray(self.s0 + self.sbs * self.n_max)
		self.buff_mv = memoryview(self.buff)
		self.buff_mv_err = self.buff_mv[:self.ebs]
		self.lock = asyncio.Lock() # to avoid read/write races

	def sample_mv(self, ts):
		# Returns memoryview to store new sample into
		pos = self.s0 + self.n * self.sbs
		if self.buff[pos:pos+4] == self.blk_skip: self.n_skips -= 1
		if self.n_ts is not None and (
				td := time.ticks_diff(ts, self.n_ts) - self.n_td ) > self.n_td:
			self.sample_mv_commit(ts, td)
			return self.sample_mv(ts + self.n_td)
		return self.buff_mv[pos:pos+self.sbs]

	def sample_mv_commit(self, ts, td_skip=None):
		# Mark current/last returned sample_mv as used and advance cursor
		if td_skip: # skip block, storing skipped time-delta in it
			if pos := self.skip_last_pos: # collapse repeated blk_skip, if any
				td_skip += self.n_td + int.from_bytes(self.buff[pos+4:pos+8], 'big')
				self.n -= 1
			else:
				pos = self.skip_last_pos = self.s0 + self.n * self.sbs
				self.buff[pos:pos+4] = self.blk_skip
				self.n_skips += 1
			if td_skip > 0xffffffff: # >50d delta = overflow - flush all old data
				self.n_ts = None; self.n = self.n_loops = self.n_skips = 0; return
			self.buff[pos+4:pos+8] = td_skip.to_bytes(4, 'big')
		else: self.skip_last_pos = None
		self.n_ts, self.n = ts, (self.n + 1) % self.n_max
		if not self.n: self.n_loops += 1

	def data_chunks(self):
		if not self.n: return [self.buff_mv[self.s0:]] if self.n_loops else []
		n = self.s0 + self.n * self.sbs
		return ( [self.buff_mv[self.s0:n]]
			if not self.n_loops else [self.buff_mv[n:], self.buff_mv[self.s0:n]] )

	def data_samples_count(self):
		return (self.n_max if self.n_loops else self.n) - self.n_skips

	def data_samples_raw(self):
		# Yields (offset_ms, sample_bytes) tuples in reverse-chronological order
		# Time offsets are positive integers (from now into past), and can be irregular
		td = time.ticks_diff(time.ticks_ms(), self.n_ts or 0)
		for chunk in reversed(self.data_chunks()):
			pos = len(chunk)
			while (pos := pos - self.sbs) >= 0:
				if chunk[pos:pos+4] != self.blk_skip:
					yield (td, bytes(chunk[pos:pos+self.sbs]))
					td += self.n_td
				else: td += int.from_bytes(chunk[pos+4:pos+8], 'big')

	def data_samples(self, ts_now=0):
		# Yields (ts, sample) values, with ts = approx posix timestamp in seconds,
		#   and sample is (pm10, pm25, pm40, pm100, rh, t, voc, nox) tuple of values,
		#   in reverse-chronological order (newest sample first).
		# Values are either float, or None if sensor returns N/A -
		#   - can mean not ready yet, not supported by this model, broken hw, etc.
		# Current timestamp to offset all samples from must be provided, or will be 0
		for td_ms, sample_raw in self.data_samples_raw():
			yield (ts_now - (td_ms / 1000), self.s_parse(sample_raw))

	def data_errors(self): # returns tuple of error strings, if any
		return self.errs_parse(self.buff_mv[:self.s0])


class WebUI:

	class Req:
		prefix, cache_gen, etag, bs = '', 0, b'-no-header-', 0
		mime_types = dict(js='text/javascript', ico='image/vnd.microsoft.icon')
		def __init__(self, **kws): self.update(**kws)
		def update(self, **kws):
			for k,v in kws.items(): setattr(self, k, v)

	def __init__( self, srb, verbose=False,
			page_title=AQMConf.webui_title,
			url_prefix=AQMConf.webui_url_prefix,
			d3_api=AQMConf.webui_d3_api,
			d3_remote=AQMConf.webui_d3_load_from_internet,
			marks_bs_max=AQMConf.webui_marks_storage_bytes,
			fan_clean_func_iter=val_iter() ):
		self.srb, self.verbose = srb, verbose
		self.req_n, self.req_lock = 0, asyncio.Lock()
		self.d3_api, self.d3_remote = d3_api, d3_remote
		self.url_prefix, self.url_strip = url_prefix, url_prefix.encode()
		self.buff = bytearray(2048); self.buff_mv = memoryview(self.buff)
		self.marks, self.marks_bs_max = None, marks_bs_max
		self.page_title, self.act_fan_clean_iter = page_title, fan_clean_func_iter
		self.req_url_map = dict(
			page_index=(b'/', b'/index.html', b'/index.htm'), favicon=(b'/favicon.ico',),
			js=(b'/webui.js',), js_d3=(f'/d3.v{self.d3_api}.min.js'.encode(),),
			data_csv=(b'/data/all/latest-first/samples.csv',),
			data_bin=(b'/data/all/latest-first/samples.8Bms_16Bsen5x_tuples.bin',),
			data_raw=(b'/data/all/latest-first/samples.debug.raw',),
			data_marks=(b'/data/marks.bin',), act_fan_clean=(b'/fan-clean',) )
		self.req_url_links = dict(( k, self.url_prefix +
			url[0].decode().lstrip('/') ) for k, url in self.req_url_map.items())
		self.req_url_locks = dict.fromkeys(
			['data_csv', 'data_bin', 'data_raw'], self.srb.lock )

	async def request(self, sin, sout):
		try: await self._request(sin, sout)
		finally:
			sin.close(); sout.close()
			await asyncio.gather(sin.wait_closed(), sout.wait_closed())

	async def _request(self, sin, sout):
		self.req_n += 1
		req = self.Req( sin=sin, sout=sout, url_map=self.req_url_map,
			url_links=self.req_url_links, url_locks=self.req_url_locks,
			log=self.verbose and (lambda *a,_pre=f'[http.{self.req_n:03d}]': print(_pre, *a)) )
		req.log and req.log('Connected:', req.sin.get_extra_info('peername'))
		line = (await sin.readline()).strip()
		try: req.verb, req.url, req.proto = line.split(None, 2)
		except ValueError: return req.log and req.log('Req non-http line:', line)
		req.log and req.log(f'Request: {req.verb.decode()} {req.url.decode()}')
		if self.url_strip and req.url.startswith(self.url_strip):
			req.url = req.url[len(self.url_strip):]
		await self.req_lock.acquire() # avoids transfer-buffer clashes
		try: await self.req_handler(req)
		except Exception as err:
			if isinstance(err, OSError) and err.errno == 104: pass # ECONNRESET
			else: req.log and req.log(f'Request-exc: {err_fmt(err)}')
		finally: self.req_lock.release()

	def res_err(self, req, code, msg={
			400: 'Bad Request', 405: 'Method Not Allowed',
			413: 'Payload Too Large', 404: 'Not Found', 429: 'Too many requests' }):
		if isinstance(msg, dict): msg = msg.get(code, '')
		req.log and req.log(f'Response: http-error-{code} [{msg or "-"}]')
		req.sout.write(f'HTTP/1.0 {code} {msg}\r\n'.encode())
		body = ( f'HTTP Error [{code}]: {msg}\n'
			if msg else f'HTTP Error [{code}]\n' ).encode()
		req.sout.write(b'Server: aqm\r\nContent-Type: text/plain\r\n')
		req.sout.write(f'Content-Length: {len(body)}\r\n\r\n'.encode())
		req.sout.write(body)

	def res_ok(self, req, cache=None):
		if req.verb != b'get': return self.res_err(req, 405)
		if cache:
			etag = 0xcbf29ce484222325 # 64b FNV-1a hash
			for b in f'{req.cache_gen}.{cache}'.encode():
				etag = ((etag ^ b) * 0x100000001b3) % 0x10000000000000000
			etag = f'"{etag.to_bytes(8, "big").hex()}"'.encode()
			if etag == req.etag:
				req.log and req.log(f'ETag-cache-match-304: {etag.decode()}')
				req.sout.write(b'HTTP/1.0 304 Not Modified\r\nServer: aqm\r\n\r\n')
				return
		req.sout.write(b'HTTP/1.0 200 OK\r\nServer: aqm\r\n')
		if not cache: req.sout.write(b'Cache-Control: no-cache\r\n')
		else:
			req.log and req.log( 'ETag-cache-miss:'
				f' {etag.decode()} (data) vs {req.etag.decode()} (request)' )
			req.sout.write(b'ETag: ' + etag + b'\r\n')
		return True

	async def res_static(self, req, p):
		if req.verb != b'get': return self.res_err(req, 405)
		mime = req.mime_types.get(
			p.rpartition('.')[-1], 'application/octet-stream' )
		for p in [f'{p}.gz', p]:
			try: src = open(p, 'rb'); break
			except OSError: pass
		else: return self.res_err(req, 404)
		src_mtime, src_bs = os.stat(p)[-1], src.seek(0, 2) # SEEK_END
		if not self.res_ok(req, f'{p}.{src_mtime}.{src_bs}'): return
		req.sout.write(
			b'Content-Type: {mime}\r\nContent-Length: {bs}\r\n{enc}'
			.format( mime=mime, bs=src_bs,
				enc='Content-Encoding: gzip\r\n\r\n' if p.endswith('.gz') else '\r\n' ) )
		src.seek(0)
		while True:
			if n := src.readinto(self.buff_mv):
				req.sout.write(self.buff_mv[:n])
				await req.sout.drain()
			if src.tell() >= src_bs: break

	async def req_handler(self, req):
		req.ts, req.verb = time.ticks_ms(), req.verb.lower()
		while b'//' in req.url: req.url = req.url.replace(b'//', b'/')
		while line := (await req.sin.readline()).strip():
			k, _, v = line.partition(b':')
			if (k := k.strip().lower()) == b'if-none-match': req.etag = v.strip()
			elif k == b'content-length': req.bs = int(v)
		for k, k_url in req.url_map.items():
			if req.url not in k_url: continue
			req.log and req.log(f'Handler: {k}')
			if lock := req.url_locks.get(k): await lock.acquire()
			try: await getattr(self, f'req_{k}')(req)
			finally:
				if lock: lock.release()
			break
		else: self.res_err(req, 404)
		await req.sout.drain(); req.sout.close()
		req.log and req.log(f'Done [ {time.ticks_diff(time.ticks_ms(), req.ts):,d} ms]')

	async def req_page_index(self, req):
		if not self.res_ok(req): return
		req.sout.write(b'Content-Type: text/html\r\n')
		if sen_actions := next(self.act_fan_clean_iter):
			sen_actions = (
				'\n<li><a href=\'{url}\'>Run fan cleaning</a> (at least every week)\n'
				.format(url=req.url_links['act_fan_clean']) )
		if err_msgs := self.srb.data_errors():
			err_msgs = '\n'.join(
				f'<li>{webui_err_msgs.get(err) or "Unknown error [{}]".format(err)}'
				for err in err_msgs )
		body = webui_body.strip().replace(b'\t', b'  ').format(
			title=self.page_title,
			sen_actions=sen_actions or '', err_msgs=err_msgs or '',
			d3_api=self.d3_api, d3_from_cdn=int(self.d3_remote),
			marks_bs_max=self.marks_bs_max,
			**dict((f'url_{k}', url) for k, url in req.url_links.items()) )
		page_bs = len(webui_head) + len(body)
		req.sout.write(f'Content-Length: {page_bs}\r\n\r\n'.encode())
		req.sout.write(webui_head); req.sout.write(body)

	def req_favicon(self, req): return self.res_static(req, 'favicon.ico')
	def req_js(self, req): return self.res_static(req, 'webui.js')
	def req_js_d3(self, req): return self.res_static(req, f'd3.v{self.d3_api}.min.js')

	async def req_data_marks(self, req):
		if req.verb == b'get':
			req.sout.write(
				b'HTTP/1.0 200 OK\r\nServer: aqm\r\n'
				b'Content-Type: application/octet-stream\r\n'
				b'Cache-Control: no-cache\r\n'
				b'X-Format: [ uint8 label-length || uint8 color'
					b' || uint32 posix-time || label-utf8 ]* || \\x00\r\n' )
			if not self.marks:
				req.log and req.log('Marks: empty buffer')
				req.sout.write(b'Content-Length: 1\r\n\r\n\0')
			else:
				req.log and req.log(f'Marks: sending {self.marks_bs:,d}B')
				req.sout.write(f'Content-Length: {self.marks_bs}\r\n\r\n'.encode())
				req.sout.write(self.marks_mv[:self.marks_bs])
		elif req.verb == b'put':
			if not self.marks:
				self.marks, self.marks_bs = bytearray(self.marks_bs_max), 1
				self.marks_mv = memoryview(self.marks)
			if req.bs > len(self.marks_mv): return self.res_err(req, 413)
			self.marks_bs = await req.sin.readinto(self.marks_mv[:req.bs])
			req.log and req.log(f'Marks: received {self.marks_bs:,d} / {req.bs:,d} B')
			if self.marks_bs != req.bs:
				self.marks[0], self.marks_bs = 0, 1
				req.log and req.log('Marks: error - incomplete data read')
				return self.res_err(req, 400)
			req.sout.write(b'HTTP/1.0 204 No Content\r\nServer: aqm\r\n\r\n')
		else: self.res_err(req, 405)

	async def req_data_bin(self, req):
		if not self.res_ok(req): return
		req.sout.write(
			b'Content-Type: application/octet-stream\r\n'
			b'X-Format: [ 8B double time-offset ms || 16B SEN5x sample ]*\r\n' )
		buff, bs = self.buff_mv[:24], self.srb.data_samples_count() * 24
		req.sout.write(f'Content-Length: {bs}\r\n\r\n'.encode())
		for n, (td, sample) in enumerate(self.srb.data_samples_raw()):
			struct.pack_into('>d16s', buff, 0, float(td), sample)
			req.sout.write(buff)
			if not n % 80: await req.sout.drain()

	async def req_data_raw(self, req):
		if not self.res_ok(req): return
		req.sout.write(
			b'Content-Type: application/octet-stream\r\n'
			b'X-Format: Raw SampleRingBuffer contents for debugging\r\n' )
		n, buff_bs, bs = 0, len(buff := self.srb.buff_mv), len(self.buff)
		req.sout.write(f'Content-Length: {buff_bs}\r\n\r\n'.encode())
		while n < buff_bs:
			req.sout.write(buff[n:n+bs])
			await req.sout.drain()
			n += bs

	async def req_data_csv(self, req):
		if not self.res_ok(req): return
		req.sout.write(b'Content-Type: text/csv\r\n')
		header = b'time_offset, pm10, pm25, pm40, pm100, rh, t, voc, nox\n'
		line_base = ( b' 123456.0, 123.0, 123.0,'
			b' 123.0, 123.0, 12.34, 12.345, 1234.0, 1234.0\n' )
		(line := self.buff_mv[:len(line_base)])[:] = line_base
		bs = len(header) + self.srb.data_samples_count() * len(line)
		req.sout.write(f'Content-Length: {bs}\r\n\r\n'.encode())
		req.sout.write(header)
		# for f in line.rstrip().split(b','): fields.append((n, m:=len(f))); n+=m+1
		fields = (0,9),(10,6),(17,6),(24,6),(31,6),(38,6),(45,7),(53,7),(61,7)
		fmt = dict((vlen, f'{{:>{vlen}}}') for pos,vlen in fields)
		for n, (ts, sample) in enumerate(self.srb.data_samples()):
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
			if not n % 20: await req.sout.drain()

	async def req_act_fan_clean(self, req):
		if req.verb != b'get': return self.res_err(req, 405)
		if not (fan_clean_func := next(self.act_fan_clean_iter)): return self.res_err(req, 429)
		await fan_clean_func()
		req.sout.write(b'HTTP/1.0 302 Found\r\nServer: aqm\r\n')
		req.sout.write(f'Location: {req.url_links["page_index"] or "/"}\r\n\r\n'.encode())


class UDPAlerts:

	keys = 'pm', 'pm', 'pm', 'pm', 'rh', 't', 'voc', 'nox'

	@staticmethod
	def addr_key(addr):
		if '.' in addr: return bytes(int(v) for v in addr.split('.'))
		raise NotImplementedError # listening addrs are IPv4 anyway

	@classmethod
	def create_if_needed(cls, conf):
		bounds, nx = list(), conf.alerts_nx
		for n, k in enumerate(cls.keys):
			a, b = (getattr(conf, f'alerts_{b}_{k}', nx) for b in ('min', 'max'))
			a_nx, b_nx = a == nx, b == nx
			if a_nx and b_nx: continue
			elif a_nx: a = -999.0
			elif b_nx: b = 999.0
			bounds.append((n, k, a, b))
		if not ( (bounds := tuple(bounds))
			and (dst_list := conf.alerts_send_to.split()) ): return
		if not socket:
			return p_err( 'Socket API not supported in'
				' micropython firmware, not enabling UDP alerts' )
		dst_addrs = dict()
		for n, sock in enumerate(dst_list):
			addr, _, port = sock.partition(':')
			addr = socket.getaddrinfo( addr,
				int(port or 0), socket.AF_INET, socket.SOCK_DGRAM )[0][-1]
			dst_addrs[cls.addr_key(addr[0])] = addr
		return UDPAlerts( conf.alerts_bind_port,
			dst_addrs, bounds, verbose=conf.alerts_verbose )

	def __init__(self, bind_port, dst_addrs, bounds, verbose=False):
		self.dst_addrs, self.bounds, self.snooze_ts = dst_addrs, bounds, dict()
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self.sock.bind(('0.0.0.0', bind_port))
		self.sock.setblocking(False)
		self.log = verbose and (lambda *a: print('[alerts]', *a))
		self.log and self.log( 'Checking/sending UDP-alerts to'
			f' {len(self.dst_addrs)} host(s) ({len(self.bounds)} bounds)' )

	def crc16(self, s, crc=0):
		# CRC-16F/5 CRC-16-OpenSafety-A {241,241,241,35,10,8,3}
		# See https://users.ece.cmu.edu/~koopman/crc/crc16.html
		for c in s:
			m = 0x100
			while m := m >> 1:
				bit = bool(crc & 0x8000) ^ bool(c & m)
				crc <<= 1
				if bit: crc ^= 0x5935
			crc &= 0xffff
		return crc & 0xffff

	def check(self, data, sample):
		ts = time.ticks_ms()
		while True:
			try: pkt, addr = self.sock.recvfrom(128)
			except OSError as err:
				if err.errno == 11: break # EAGAIN
				raise
			if self.crc16(pkt[:-2]) != int.from_bytes(pkt[-2:], 'big'):
				self.log and self.log(f'pkt crc16-mismatch {addr}')
			try:
				(td,), errs = struct.unpack('>d', pkt[:8]), pkt[8:-2]
				errs = set(self.keys).intersection(errs.decode().split())
				if not errs: raise ValueError('no alert-keys to suppress')
			except ValueError as err:
				self.log and self.log(f'pkt processing error {addr}: {err_fmt(err)}')
			if (ak := self.addr_key(addr[0])) not in self.dst_addrs:
				self.log and self.log(f'skipping pkt from unknown source {addr}')
				continue
			ts_pkt = time.ticks_add(ts, int(td * 1000))
			for key in errs: self.snooze_ts[ak, key] = ts_pkt
			self.log and self.log(f'updated snooze-ts for keys {addr}: {errs}')

		errs = set()
		for n, k, a, b in self.bounds:
			if not a <= data[n] <= b: errs.add(k)
		if not errs: return # all within bounds

		ts, dst_addrs = time.ticks_ms(), list()
		for ak, addr in self.dst_addrs.items():
			for key in errs:
				if not (ts_snooze := self.snooze_ts.get((ak, key))): break
				if time.ticks_diff(ts, ts_snooze) >= 0: del self.snooze_ts[ak, key]; break
			else: continue
			dst_addrs.append(addr)
		if not dst_addrs: return # all suppressed

		pkt = sample + ' '.join(sorted(errs)).encode()
		pkt += self.crc16(pkt).to_bytes(2, 'big')
		self.log and self.log( 'sending alert pkt to'
			f' {len(dst_addrs)} addr(s) [ {len(pkt):,d} B]: {errs}' )
		for addr in dst_addrs:
			try: self.sock.sendto(pkt, addr)
			except OSError as err:
				if err.errno not in (11, 113): raise # EAGAIN, EHOSTUNREACH
				self.log and self.log(f'pkt send failed - {err_fmt(err)}')


async def main_aqm(conf, wifi):
	httpd = webui = None
	components, webui_opts = list(), dict()
	if wifi: components.append(wifi)

	if conf.sensor_sample_count >= 2**16: # 1 MiB ought to be enough for everybody
		return p_err('Sample count values >65536 are not supported')
	conf.sensor_sample_interval = int(conf.sensor_sample_interval * 1000)
	srb = SampleRingBuffer(
		conf.sensor_sample_interval, conf.sensor_sample_count )
	alerts = UDPAlerts.create_if_needed(conf)

	i2c = dict()
	if conf.sensor_i2c_freq: i2c['freq'] = conf.sensor_i2c_freq
	if conf.sensor_i2c_timeout: i2c['timeout'] = int(conf.sensor_i2c_timeout * 1000)
	if min(conf.sensor_i2c_n, conf.sensor_i2c_pin_sda, conf.sensor_i2c_pin_scl) < 0:
		return p_err('Sensor I2C bus/pin parameters must be set in the config file')
	i2c = machine.I2C( conf.sensor_i2c_n,
		sda=machine.Pin(conf.sensor_i2c_pin_sda),
		scl=machine.Pin(conf.sensor_i2c_pin_scl), **i2c )

	sen5x = Sen5x(i2c, conf.sensor_i2c_addr)
	if conf.sensor_reset_on_start: await sen5x('reset')
	if ( conf.sensor_temp_comp_offset
			or conf.sensor_temp_comp_slope
			or conf.sensor_temp_comp_time_const ):
		await sen5x( 'temp_offset_set',
			conf.sensor_temp_comp_offset,
			conf.sensor_temp_comp_slope,
			conf.sensor_temp_comp_time_const )
	components.append(sen5x_poller(
		sen5x, srb, td_data=conf.sensor_sample_interval,
		td_errs=int(conf.sensor_error_check_interval * 1000),
		err_rate_limit=token_bucket_iter(conf.sensor_i2c_error_limit),
		stop_on_exit=conf.sensor_stop_on_exit,
		alerts=alerts, verbose=conf.sensor_verbose ))
	webui_opts['fan_clean_func_iter'] = \
		sen5x.fan_clean_func_iter(int(conf.sensor_fan_clean_min_interval * 1000))

	if socket:
		webui = WebUI( srb, page_title=conf.webui_title,
			url_prefix=conf.webui_url_prefix, verbose=conf.webui_verbose,
			d3_api=conf.webui_d3_api, d3_remote=conf.webui_d3_load_from_internet,
			marks_bs_max=conf.webui_marks_storage_bytes, **webui_opts )
	else: p_err('Socket API not supported in micropython firmware, not starting WebUI')

	print('--- AQM start ---')
	try:
		if webui:
			httpd = await asyncio.start_server( webui.request,
				'0.0.0.0', conf.webui_port, backlog=conf.webui_conn_backlog )
			components.append(httpd.wait_closed())
		await asyncio.gather(*components)
	finally:
		if httpd: httpd.close(); await httpd.wait_closed() # to reuse socket for err-msg
		print('--- AQM stop ---')

async def main_fail_webui_req(fail, fail_ts, sin, sout, _html=(
		b'<!DOCTYPE html>\n<head><meta charset=utf-8>\n'
		b'<style>\nbody { margin: 0 auto; padding: 1em;\n'
		b' max-width: 960px; color: #d2f3ff; background: #09373b; }\n'
		b'a, a:visited { color: #5dcef5; } p { font-weight: bold; }\n</style>\n'
		b'<body><h2>Fatal Error - Unexpected component failure</h2>\n<pre>' )):
	try:
		fid, td = (str(v).encode() for v in [fail_ts, time.ticks_diff(time.ticks_ms(), fail_ts)])
		try:
			verb, url, proto = (await sin.readline()).split(None, 2)
			if url.lower().endswith(b'/reset.' + fid): return machine.reset()
		except ValueError: pass
		while (await sin.readline()).strip(): pass # flush request
		sout.write( b'HTTP/1.0 500 Server Error\r\nServer: aqm\r\n'
			b'Cache-Control: no-cache\r\nContent-Type: text/html\r\n' )
		tail = b'''</pre>\n<div id=tail><script>
			let tz = Intl.DateTimeFormat().resolvedOptions().timeZone,
				dt = new Intl.DateTimeFormat('sv-SE', {
					timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
					hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
				.format(new Date(Date.now() - %td))
			document.getElementById('tail').innerHTML =
				`<p>Error date/time: ${dt} [${tz}]</p><a href=reset.%fid>Reset Device</a>`
			</script>'''.replace(b'\t', b' ').replace(b'%fid', fid).replace(b'%td', td)
		sout.write(f'Content-Length: {len(_html) + len(fail) + len(tail)}\r\n\r\n')
		sout.write(_html); sout.write(fail); sout.write(tail)
		await sout.drain()
	finally:
		sin.close(); sout.close()
		await asyncio.gather(sin.wait_closed(), sout.wait_closed())

async def main():
	print('--- AQM init ---')
	wifi, conf = None, conf_parse('config.ini')

	if conf.wifi_ap_conf or conf.wifi_sta_aps:
		if not getattr(network, 'WLAN', None):
			p_err('No networking/wifi support detected in micropython firmware, aboring')
			return p_err('Either remove/clear [wifi-*] config section(s) or replace device/firmware')
		if conf.wifi_ap_conf: wifi_ap_setup(conf.wifi_ap_conf)
		else: wifi = asyncio.create_task(wifi_client(conf.wifi_sta_conf, conf.wifi_sta_aps))

	fail = None
	try: return await main_aqm(conf, wifi)
	except Exception as err: fail = err
	fail_ts = time.ticks_ms()

	gc.collect() # in case it was a mem shortage
	gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())

	import sys, io
	p_err('One of the main components failed, traceback follows...')
	sys.print_exception(fail)
	if not socket: return # no way to display fail-webui - just exit

	err = io.BytesIO()
	sys.print_exception(fail, err)
	err, fail = None, err.getvalue()
	fail = fail.replace(b'&', b'&amp;').replace(b'<', b'&lt;').replace(b'>', b'&gt;')

	if wifi and wifi.done():
		p_err('[wifi] Connection monitoring task failed, restarting it')
		wifi = wifi_client(conf.wifi_sta_conf, conf.wifi_sta_aps)

	p_err('Starting emergency-WebUI with a traceback page')
	httpd = await asyncio.start_server(
		lambda sin, sout: main_fail_webui_req(fail, fail_ts, sin, sout),
		'0.0.0.0', conf.webui_port, backlog=conf.webui_conn_backlog )
	await asyncio.gather(httpd.wait_closed(), *([wifi] if wifi else []))
	raise RuntimeError('BUG - fail-webui stopped unexpectedly')

def run(): asyncio.run(main())
if __name__ == '__main__': run()
