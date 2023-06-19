import re, network, uasyncio as asyncio


class AQMConf:

	wifi_ap_base = dict(
		scan_interval=20.0, check_interval=10.0 )
	wifi_ap_map = dict()

	chart_samples = 100

p_err = lambda *a: print('ERROR:', *a)
err_fmt = lambda err: f'[{err.__class__.__name__}] {err}'


def conf_parse(conf_file):
	conf = AQMConf()
	with open(conf_file) as src: conf_str = src.read().replace('\r', '')
	bool_map = {
		'1': True, 'yes': True, 'y': True, 'true': True, 'on': True,
		'0': False, 'no': False, 'n': False, 'false': False, 'off': False }

	if sec := re.search('(?:^|\n)\s*\[wifi\]\s*\n(.*)(?:\n\s*\[|$)', conf_str):
		ap_map = {None: conf.wifi_ap_base}
		ap_keys = dict(
			scan_interval=float, check_interval=float,
			key=str, hostname=str, channel=int, reconnects=int,
			txpower=float, mac=lambda v: v.encode(),
			hidden=lambda v: bool_map[v], pm=lambda v: getattr(network.WLAN, f'PM_{v}') )
		ssid, ap, sec = None, dict(), sec.group(1).splitlines() + ['ssid=']
		for line in sec:
			key, sep, val = map(str.strip, line.partition('='))
			key_conf = key.replace("-", "_").lower()
			if not key or key[0] in '#;': continue
			elif key == 'country': ap_map[None][key] = val
			elif key == 'verbose': ap_map[None][key] = bool_map[val]
			elif key == 'ssid':
				if ssid and not ap:
					p_err(f'[conf.wifi] Skipping ssid without config [ {ssid} ]')
				else:
					if ssid not in ap_map: ap_map[ssid] = ap_map[None].copy()
					ap_map[ssid].update(ap, ssid=ssid)
					ap.clear()
				ssid = val
			elif key_func := ap_keys.get(key_conf):
				try: ap[key_conf] = key_func(val)
				except Exception as err:
					p_err(f'[conf.wifi]: Failed to process [ {ssid} ] {key}=[ {val} ]: {err_fmt(err)}')
			else: p_err(f'[conf.wifi] Unrecognized config key [ {key} ]')
		conf.wifi_ap_base, conf.wifi_ap_map = ap_map.pop(None), ap_map

	if sec := re.search('(?:^|\n)\s*\[chart\]\s*\n(.*)(?:\n\s*\[|$)', conf_str):
		for line in sec.group(1).splitlines():
			key, sep, val = map(str.strip, line.partition('='))
			key_conf = f'chart_{key.replace("-", "_").lower()}'
			if not key or key[0] in '#;': continue
			elif (val_conf := getattr(conf, key_conf, None)) is None:
				p_err(f'[conf.chart] Skipping unrecognized config key [ {key} ]')
			else:
				if isinstance(val_conf, (int, float)): val = type(val_conf)(val)
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


async def main():
	print('--- AQM start ---')
	conf = conf_parse('config.ini')
	tasks = set()

	if conf.wifi_ap_map:
		tasks.add(asyncio.create_task(
			wifi_client(conf.wifi_ap_base, conf.wifi_ap_map) ))

	try: await asyncio.gather(*tasks)
	finally: print('--- AQM stop ---')

asyncio.run(main())
