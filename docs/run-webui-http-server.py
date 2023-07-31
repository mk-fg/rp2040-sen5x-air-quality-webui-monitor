#!/usr/bin/env python

# Same as "python -m http.server" with disabled caching,
#  and serving .gz files as-is with added content-encoding header.

import os, sys, mimetypes, pathlib as pl, http.server as srv


class ReqHandler(srv.SimpleHTTPRequestHandler):
	extensions_map = mimetypes.read_mime_types('/etc/mime.types')
	comp_ext, comp_name = '.gz', 'gzip'

	def guess_type(self, path):
		if path.endswith(self.comp_ext): path = path[:-len(self.comp_ext)]
		return super().guess_type(path)

	def parse_request(self):
		self.path_compressed = False
		res = super().parse_request()
		for k in 'If-Modified-Since If-None-Match'.split():
			if k in self.headers: del self.headers[k] # disable http.server caches
		return res

	def translate_path(self, path):
		path = super().translate_path(path)
		if not (p := pl.Path(path)).exists():
			p = p.parent.parent / p.name # up from docs/ into repo dir
			if p.exists(): path = str(p)
			elif (p.parent / (p.name + self.comp_ext)).exists():
				self.path_compressed, path = True, str(p) + self.comp_ext
		return path

	def end_headers(self):
		self._headers_buffer.append(
			b'Cache-Control: no-cache\r\n' )
		if self.path_compressed:
			self._headers_buffer.append(
				f'Content-Encoding: {self.comp_name}\r\n'.encode() )
		self._headers_buffer.append(b'\r\n')
		self.flush_headers()


os.chdir(pl.Path(__file__).resolve().parent)
with srv.ThreadingHTTPServer(('0.0.0.0', 8000), ReqHandler) as httpd:
	host, port = httpd.socket.getsockname()[:2]
	url_host = f'[{host}]' if ':' in host else host
	print(f'Serving HTTP on {host} port {port}: http://{url_host}:{port}/')
	try: httpd.serve_forever()
	except KeyboardInterrupt: pass
