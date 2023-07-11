#!/usr/bin/env python

import os, sys, re, base64, gzip, argparse, textwrap, pathlib as pl

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
	parser.add_argument('-o', '--output-html',
		metavar='file', default='snapshot.html',
		help='Path to resulting/output HTML file. Default: %(default)s')
	opts = parser.parse_args()

	p_repo = pl.Path(__file__).resolve().parent.parent
	p_out_html = pl.Path(opts.output_html).resolve()
	p_data_bin = pl.Path(opts.data_bin).resolve()

	data = p_data_bin.read_bytes()
	data_ts = p_data_bin.stat().st_mtime
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
