#!/usr/bin/env python3
"""Inject course_data.json and elevation_sources.json into template.html -> index.html."""
tpl = open("template.html").read()
data = open("course_data.json").read()
elev = open("elevation_sources.json").read()
assert "/*__DATA__*/" in tpl, "template data placeholder missing"
assert "/*__ELEV__*/" in tpl, "template elevation placeholder missing"
out = tpl.replace("/*__DATA__*/", data).replace("/*__ELEV__*/", elev)
open("index.html", "w").write(out)
print("wrote index.html")
