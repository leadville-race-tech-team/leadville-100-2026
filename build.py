#!/usr/bin/env python3
"""Inject course_data.json into template.html -> index.html (the deployable page)."""
tpl = open("template.html").read()
data = open("course_data.json").read()
assert "/*__DATA__*/" in tpl, "template placeholder missing"
open("index.html", "w").write(tpl.replace("/*__DATA__*/", data))
print("wrote index.html")
