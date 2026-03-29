from Deadline.Scripting import RepositoryUtils

lg = RepositoryUtils.GetLimitGroup("nuke", True)
for attr in sorted(dir(lg)):
    if "lave" in attr.lower() or "exclude" in attr.lower() or "list" in attr.lower():
        try:
            val = getattr(lg, attr)
            print("{0} = {1}".format(attr, val))
        except:
            print("{0} = <method>".format(attr))
