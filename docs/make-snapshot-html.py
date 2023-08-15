#!/usr/bin/env python

import pathlib as pl, datetime as dt
import os, sys, re, base64, gzip, argparse, textwrap

dd = lambda text: re.sub( r' \t+', ' ',
	textwrap.dedent(text).strip('\n') + '\n' ).replace('\t', '  ')

def main(argv=None):
	parser = argparse.ArgumentParser(
		formatter_class=argparse.RawTextHelpFormatter,
		description=dd('''
			Create self-contained HTML visualization page from
				rp2040-sen5x-aqm samples.8Bms_16Bsen5x_tuples.bin data file.
			Needs to be run from a project repository, to embed base
				HTML/JS files there into resulting output along with the data.'''))
	parser.add_argument('data_bin', help=dd('''
		samples.8Bms_16Bsen5x_tuples.bin data file downloaded from the device.
		File's modification time (mtime) is important, and is used
			as a time when data snapshot was taken mark,
			with times of all data samples within the file offset relative to that.'''))
	parser.add_argument('-t', '--datetime-from-filename', action='store_true', help=dd('''
		Use iso8601 timestamp in the filename as
			a time of data export, instead of file modification time.
		Filename example: data.2023-08-08T07:46:46.bin'''))
	parser.add_argument('-o', '--output-html',
		metavar='file', default='snapshot.html',
		help='Path to resulting/output HTML file. Default: %(default)s')
	opts = parser.parse_args()

	p_repo = pl.Path(__file__).resolve().parent.parent
	p_out_html = pl.Path(opts.output_html).resolve()
	p_data_bin = pl.Path(opts.data_bin).resolve()

	data = p_data_bin.read_bytes()
	if opts.datetime_from_filename:
		if not (m := re.search( r'(^|.)(\d{4}-\d{2}-\d{2}'
				r'([ T])\d{2}:\d{2}:\d{2})(.|$)', opts.data_bin )):
			parser.error( 'Failed to regexp-match iso8601'
				f' date/time in the filename: {opts.data_bin}' )
		data_ts = dt.datetime.fromisoformat(m[2]).timestamp()
	else: data_ts = p_data_bin.stat().st_mtime

	html = (p_repo / 'docs/index.html').read_text()
	html = html.replace('<head>', dd('''
		<head>
		<meta http-equiv=content-security-policy content="
			default-src 'none'; font-src 'self'; img-src 'self';
			style-src 'unsafe-inline'; media-src 'self'; script-src 'unsafe-inline';">''' ))

	# All body stuff other than graph shouldn't be needed
	html = html[:html.index('<body>')+6] + '\n<div id=graph><svg></svg></div>\n'

	with gzip.open(p_repo / 'd3.v7.min.js.gz') as d3_src:
		script_d3 = f'<script>\n{d3_src.read().decode().strip()}\n</script>'
	script_webui = f'<script>\n{(p_repo / "webui.js").read_text().strip()}\n</script>'
	script_data = dd(f'''
		<script>
		let b64 = '{base64.b64encode(data).decode()}'
		window.aqm_opts = {{
			time_now: {int(data_ts)},
			d3_try_local: 0,
			d3_from_cdn: 0,
			data: new DataView(
				Uint8Array.from(atob(b64), c => c.charCodeAt(0)).buffer ) }}
		</script>''')

	html += f'\n{script_d3}\n\n{script_data}\n\n{script_webui}'

	p_out_html.write_text(html)

if __name__ == '__main__': sys.exit(main())
