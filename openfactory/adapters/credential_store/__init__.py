"""The credential store axis — WHERE a stored secret is read from, named by a reference (#742).

The `credential` axis next door says how a VENDOR turns what it holds into a token. This one says
where a secret the deployment STORES comes from: the process environment, a file mounted into the
process the way container platforms deliver secrets, or whatever an add-on's row reads. Every
credential the core reads goes through `registry.stored` (a deployment credential, by the variable
name it has always had) or `registry.resolve` (a reference a registry entry names), so a
deployment whose secrets live in mounted files no longer has to copy each one into a variable
first. See `registry.py`.
"""
