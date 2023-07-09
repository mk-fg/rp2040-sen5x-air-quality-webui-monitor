'use strict'

// D3 init

let opts = window.aqm_opts, urls = window.aqm_urls

let d3js_api = opts.d3_api || 7,
	d3js_local_load = opts.d3_try_local || !opts.d3_from_cdn, // true = try local url first
	d3js_local_url = urls.d3,
	d3js_remote_load = opts.d3_from_cdn, // false = always use local copy
	d3js_remote_url = `https://d3js.org/d3.v${d3js_api}.min.js`,
	d3js_remote_import = `https://cdn.jsdelivr.net/npm/d3@${d3js_api}/+esm`,
	d3js_loader = async res => {
		if (window.d3) return window.d3
		if (d3js_local_load) {
			res = await fetch(d3js_local_url).catch(res => res)
			if (res.ok) { eval(await res.text()); return window.d3 } }
		else if (!d3js_remote_load) return
		if (!d3js_remote_load) return console.log(
			`ERROR: Failed to load local d3.js`
			+ ` [ ${d3js_local_url} ]: ${res.status} - ${res.statusText}` )
		if (d3js_local_load)
			console.log(`WARNING: importing d3 from ${d3js_remote_import}`)
		return await import(d3js_remote_import) }

window.onload = () => d3js_loader().then(async d3 => {
if (!d3) return document.getElementById('graph').innerHTML = `
	<h2>ERROR: failed to load d3.js library</h2>
	<p>Check uMatrix/NoScript/adblocker setttings or put
		<a href='${d3js_remote_url}'>${d3js_local_url}</a> into same dir as main script.</p>`


// Shared helpers

let fetch_data = url => fetch(url).then(async res => {
		if (!res.ok) throw `HTTP Error [ ${url} ]: ${res.status} ${res.statusText}`
		return new DataView(await res.arrayBuffer()) })
	.catch(res => d3.select('#errors').append('li').text(res) && null)

let fmt_ts_tz = Intl.DateTimeFormat().resolvedOptions().timeZone,
	fmt_ts_iso8601 = ts => new Intl.DateTimeFormat('sv-SE', {
		timeZone: fmt_ts_tz, year: 'numeric', month: '2-digit', day: '2-digit',
		hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(ts))

let debounce_enabled = true // for debugging
let debounce = (delay_ms, mode, func) => {
	// Usage: s.on('input', debounce(300, 'last', (d, n, ns) => console.log(ns[n].value)))
	//  last - delay after last call; usage: not called on fast typing until delay passes
	//  now - now + delay; usage: rate-limiting calls, where first one works, next one delayed
	//  first - delay after first call; usage: same as "now" but with first call delayed as well
	let timeout, timeout_calls
	return (...args) => {
		if (!debounce_enabled) return func(...args)
		if (mode === 'now' && !timeout) func(...args)
		if (timeout) {
			timeout_calls++
			if (mode === 'last') { clearTimeout(timeout); timeout = null } }
		else timeout_calls = 0
		if (!timeout) timeout = window.setTimeout(() => {
			timeout = null; if (!(mode === 'now' && !timeout_calls)) func(...args) }, delay_ms) } }


let data, dss, ds_map, ds_text,
	ds_pmx = ['pm10', 'pm25', 'pm40', 'pm100'], ds_aux = ['voc', 'nox', 't', 'rh']
Data: {
	let fetch_samples = async ts => {
		if (!ts) ts = Date.now()
		let sbs = 24,
			sample_keys = ['ts', 'pm10', 'pm25', 'pm40', 'pm100', 'rh', 't', 'voc', 'nox'],
			sample_ks = [1, 10, 10, 10, 10, 100, 200, 10, 10],
			sample_nx = [-1, 0xffff, 0xffff, 0xffff, 0xffff, 0x7fff, 0x7fff, 0x7fff, 0x7fff],
			data_raw = await fetch_data(urls.data)
		return d3.range(0, data_raw.byteLength, sbs).map(n => {
			let vals = [data_raw.getFloat64(n)]
			vals.push.apply(vals, d3.range(n=n+8, n=n+2*4, 2).map(n => data_raw.getUint16(n)))
			vals.push.apply(vals, d3.range(n, n+2*4, 2).map(n => data_raw.getInt16(n)))
			vals = Object.fromEntries(
				d3.zip(sample_keys, vals, sample_ks, sample_nx)
					.map(([key, d, k, nx]) => [key, d === nx ? null : d / k]) )
			vals.ts = ts - vals.ts
			return vals }).sort((d1, d2) => d1.ts - d2.ts) }

	data = await fetch_samples()
	dss = d3.zip( ds_pmx,
			['PM1', 'PM2.5', 'PM4', 'PM10'],
			['#fdc28c', '#fc9346', '#eb6311', '#bb3d02'],
			[300, 400, 500, 700] )
		.map(([k, label, c, fw], n, ns) => ({
			k: k, label: label, color: c,
			line_w: 0.5 + 2.5 * (n / ns.length), font_w: fw }))
	d3.zip( ds_aux, ['VOC', 'NOx', 'T°C', 'RH%'],
			['#54e01150', '#41a6a280', '#d175c180', '#b31b7ce0'], [null, null, '5,5', '5,5'] )
		.forEach(([k, label, c, ld]) => dss.push({k: k, label: label, color: c, line_dash: ld}))
	dss = dss.filter(ds => data.some(d => d[ds.k] !== null)) // unsupported values

	ds_map = Object.fromEntries(dss.map(ds => [ds.k, ds]))
	ds_map['ts'] = {k: 'ts', fmt: fmt_ts_iso8601}
	ds_pmx = ds_pmx.filter(k => ds_map[k])
	ds_aux = ds_aux.filter(k => ds_map[k])

	ds_text = ['ts'].concat(dss.map(ds => ds.k)) // list of text lines in order
} // Data


// Chart

let margin = {top: 20, right: 130, bottom: 50, left: 70},
	sz = {w: 960 - margin.left - margin.right, h: 700 - margin.top - margin.bottom},
	x = d3.scaleTime().range([0, sz.w]).domain(d3.extent(data, d => d.ts)),
	y_pmx = d3.scaleLinear().range([sz.h, 0]).domain(
		[0, d3.max(ds_pmx.map(k => data.map(d => d[k])).flat())] ),
	ys = Object.fromEntries(
		dss.map(ds => [ ds.k, ds_pmx.includes(ds.k) ? y_pmx :
			d3.scaleLinear().range([sz.h, 0]).domain(d3.extent(data.map(d => d[ds.k]))) ]) ),
	ax = () => d3.axisBottom(x).ticks(8),
	ay_pmx = () => d3.axisLeft(y_pmx), // main Y axis
	ts_now_label = new Intl.DateTimeFormat('sv-SE', {
		timeZone: fmt_ts_tz, hour: '2-digit', minute: '2-digit',
		second: '2-digit', hour12: false }).format() + ' now'

let vis = d3.select('#graph svg')
		.attr('width', sz.w + margin.left + margin.right)
		.attr('height', sz.h + margin.top + margin.bottom)
	.append('g').attr('transform', `translate(${margin.left} ${margin.top})`)
	.call(s => {
		s.append('g').attr('class', 'x grid').call(
			ax().tickSize(sz.h, 0).tickFormat('') )
		s.append('g').attr('class', 'y grid').call(
			ay_pmx().tickSize(-sz.w, 0).tickFormat('') ) })
	.call(s => s
		.append('g')
			.attr('class', 'x axis fg').attr('transform', `translate(0 ${sz.h})`)
			.call(ax())
		.append('text')
			.attr('transform', `translate(${sz.w} 0)`)
			.attr('dx', '-1em').attr('dy', '3em')
			.style('text-anchor', 'end').text(
				`Date/time in local/browser timezone (${fmt_ts_tz}, ${ts_now_label})` ) )
	.call(s => s
		.append('g').attr('class', 'y axis fg').datum(ds_pmx).call(ay_pmx())
		.append('text')
			.attr('transform', 'rotate(-90)').attr('dx', '-1em').attr('dy', '-3em')
			.style('text-anchor', 'end').text('PMx µg/m³') )
	.call(s => ds_aux.forEach((k, n) =>
		s.append('g').attr('class', 'y axis fg').datum(k)
			.attr('transform', `translate(${sz.w + n*30} 0)`)
			.call(d3.axisRight(ys[k]))
			.call(s => s.selectAll('text')
				.style('text-anchor', 'middle')
				.attr('transform', 'rotate(60) translate(-3 -13)'))
			.append('text')
				.attr('transform', 'rotate(-90)').attr('dx', -(sz.h+10)).attr('dy', '1.5em')
				.style('text-anchor', 'end').text(ds_map[k].label)) )
	.call(s => dss.forEach(ds => ds.line = s.append('path')
		.data([data]).attr('class', `line ${ds.k}`).attr('stroke', ds.color || 'currentColor')
		.attr('stroke-width', ds.line_w || null).attr('stroke-dasharray', ds.line_dash || null)
		.attr('d', d3.line().x(d => x(d.ts)).y(d => ys[ds.k](d[ds.k]))) ))


let mark_add_ts = ts => null
Marks: {
	let data, bs_max = opts.marks_bs_max,
		// colors = i-want-hue 100 | ./color-b64sort - -Hs1 -b 09373b:40 -c d2f3ff:40 -c 81b0da
		//   -c fdc28c -c fc9346 -c eb6311 -c bb3d02  -c 54e011 -c 41a6a2 -c d175c1 -c b31b7c
		colors = ( '4bb7aa a3ea43 afa4dc 8393e4 a97439 aea672 aadddb c790e7 62e74f'
			+ ' bc6255 74454b e68960 b4699d afc2e4 a5c886 59edc1 63b7db e3bfcb 83b899 67e583'
			+ ' b8e782 e5a5d9 e45bc7 d44840 dbdcbe e03d21 daa68b 5eb966 78994e b3e8be' ).split(' '),

		parse = (d, map, dec) => {
			if (!map) { map = {}; dec = new TextDecoder() }
			let c, n = d.getUint8(0); if (!n) return map
			map[c = d.getUint8(1) % colors.length] = {
				c: c, ts: d.getUint32(2) * 1000,
				label: dec.decode(new DataView(d.buffer, d.byteOffset + 6, n)) }
			return parse(new DataView(d.buffer, d.byteOffset + 6 + n), map, dec) },
		serialize = (dv, n=0, ms, enc, m) => {
			if (!dv) {
				dv = new DataView(new ArrayBuffer(bs_max-1))
				ms = d3.sort(Object.values(mmap), (a, b) => d3.ascending(a.c, b.c))
				enc = new TextEncoder() }
			if (!(m = ms.shift())) return new DataView(dv.buffer, 0, n + 1)
			let tx = enc.encode(m.label), tx_n = tx.length
			dv.setUint8(n, tx_n)
			dv.setUint8(++n, m.c)
			dv.setUint32(++n, parseInt(m.ts / 1000))
			;(new Uint8Array(dv.buffer, n+=4, tx_n)).set(tx)
			return serialize(dv, n + tx_n, ms, enc) },

		mmap = parse(data = await fetch_data(urls.marks)),
		mmap_tx = mm => (
			d3.sort(Object.values(mm || mmap), (a, b) => d3.ascending(a.c, b.c))
				.map(d => `#${d.c} :: ${fmt_ts_iso8601(d.ts)} :: ${d.label}`)
				.join('\n') + '\n' ),
		mmap_tx_parse = (s, map) => {
			let line, tail
			if (Array.isArray(s)) { line = s.shift(); tail = s }
			else [line, ...tail] = s.split('\n')
			let [c, ts, label] = line.split('::', 3)
			c = c.trim().match(/^#(\d+)$/); ts = Date.parse((ts || '').trim()); map = map || {}
			if (c && ts) map[c[1]] = {c: parseInt(c[1]), ts: ts, label: (label || '').trim()}
			return !tail.length ? map : mmap_tx_parse(tail, map) },

		mta = d3.select('#marks').classed('hide', false).select('textarea'),
		mta_btn = d3.select('#marks button'),
		mta_update = () => {
			mta.property('value', mmap_tx())
			mta_colors_update(); mvis_update() },
		mta_commit = () => {
			try { data = serialize()
				mta_btn.property('disabled', false).attr('title', null) }
			catch (e) {
				if (!(e instanceof RangeError)) throw e
				mta_btn.property('disabled', true)
					.attr('title', `Too much data (limit=${bs_max}B)`) } },

		mta_colors = d3.select('#marks div'),
		mta_colors_update = () => mta_colors.selectAll('span')
			.data(Object.keys(mmap), d => d)
			.join( en => en.append('span').text(d => `#${d}`)
					.attr('style', d => `color: #${colors[d]};`).call(s => s.append('br')),
				up => up, ex => ex.remove() ),

		mvis = vis.append('g').attr('class', 'marks'),
		mvis_update = () => {
			mvis.selectAll('line')
				.data(Object.values(mmap), m => m.c)
				.join( en => en.append('line')
						.attr('y1', 0).attr('y2', sz.h).attr('stroke', d => `#${colors[d.c]}`),
					up => up, ex => ex.remove() )
				.attr('x1', m => x(m.ts)).attr('x2', m => x(m.ts))
			mvis.selectAll('text')
				.data(Object.values(mmap), m => m.c)
				.join( en => en.append('text').attr('dy', '-.3em')
					.attr('fill', d => `#${colors[d.c]}`).text(m => `#${m.c}`),
					up => up, ex => ex.remove() )
				.attr('x', m => x(m.ts)) }

	mta.on('input', debounce(300, 'last', (ev, d) => {
		let mtx = ev.target.value, mm = mmap_tx_parse(mtx),
			mtx_old = mmap_tx(), mtx_new = mmap_tx(mmap = mm)
		if (mtx_old === mtx_new) return
		mta_commit(); mta_colors_update(); mvis_update() }))

	mta_btn.on('click', async (ev, d) => {
		if (!data) return
		await fetch_data(new Request(urls.marks, {method: 'PUT', body: data})) })

	mark_add_ts = (ts, c=0) => {
		if (mmap[c]) return ++c < colors.length ?
			mark_add_ts(ts, c) : alert('Too many marks already')
		mmap[c] = {c: c, ts: ts, label: `mark-${c+1}`}
		mta_commit(); mta_update() },

	mta_update()
} // Marks


Focus: {
	let side = -1, // 1 or -1
		x_bisect = d3.bisector(d => d.ts).left,
		y_axes = vis.selectAll('.y.axis'),
		focus = vis
			.append('g').attr('class', 'focus').style('display', 'none')
			.call( s => s.append('line')
				.attr('x1', 0).attr('x2', 0).attr('y1', 0).attr('y2', sz.h) ),
		focus_label = focus.append('text')
			.attr('x', 10).attr('dy', '.3em')
			.attr('text-anchor', side > 0 ? 'start' : 'end')

	let del_p,
		del_ps = data.map(d => dss.map(ds => [x(d.ts), ys[ds.k](d[ds.k]), ds])).flat(),
		del = d3.Delaunay.from(del_ps)
	// vis.append('g').selectAll('path').data(del.voronoi([0, 0, sz.w, sz.h]).cellPolygons())
	// 	.join( en => en.append('path').attr('stroke', 'red')
	// 		.attr('fill', 'none'), upd => upd, ex => ex.remove() )
	// 	.attr('d', d => d ? 'M' + d.join('L') + 'Z' : null)

	let fmt_n = n => n.toFixed(1),
		fmt_line = (d, k) => { let label = ds_map[k]?.label
			return `${label ? (label+': ') : ''}${(ds_map[k]?.fmt || fmt_n)(d[k])}` }

	let focus_call = func => (ev, d) => { // calls func(d, ds)
		if (data.length < 2) return
		let [px, py] = d3.pointer(ev),
			x0 = x.invert(px), n = x_bisect(data, x0, 1)
		if (x0 - data[n-1].ts <= data[n] - x0) n -= 1
		func(data[n], del_ps[del_p = del.find(px, py, del_p)][2]) }

	let focus_hl_line = hl_set => {
		let hs_ds = hl_set || ((k, a, b) => b), hs_ax = hl_set || (() => true)
		dss.forEach(ds => ds
			.line?.attr('stroke', hs_ds(ds.k, 'currentColor', ds.color))
			.attr('stroke-width', hs_ds(ds.k, 2, ds.line_w || null)))
		y_axes.classed('fg', d => d.some ? d.some(k => hs_ax(k)) : hs_ax(d)) }

	vis.append('rect')
		.attr('class', 'overlay').attr('width', sz.w).attr('height', sz.h)
		.on('click', focus_call((d, ds) => mark_add_ts(d.ts)))
		.on('mouseover', (ev, d) => focus.style('display', null))
		.on('mouseout', (ev, d) => { focus.style('display', 'none'); focus_hl_line() })
		.on('mousemove', focus_call((d, ds) => {
			let hl_set = ( k_hl =>
				(k, hl=true, no_hl=null) => (k_hl && k === k_hl) ? hl : no_hl )(ds?.k)
			focus_hl_line(hl_set)
			focus.attr('transform', `translate(${x(d.ts)} 0)`)
			focus_label.selectAll('tspan').call( s => s
				.data(ds_text.filter(k => d[k] !== null), d => d)
				.join(
					en => en.append('tspan')
						.attr('dy', '1.5em').attr('x', `${side}em`)
						.attr('fill', k => ds_map[k].color?.slice(0, 7) || 'currentColor')
						.attr('font-weight', k => ds_map[k]?.font_w || null),
					upd => upd, ex => ex.remove() )
				.text(k => fmt_line(d, k)).classed('hl', k => hl_set(k)) ) }))
} // Focus

})
