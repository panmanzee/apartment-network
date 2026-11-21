from users.models import Token, User
u = User.objects.get(username="admin")
TOK = "0123456789abcdef0123456789abcdef01234567"
if not Token.objects.filter(user=u).exists():
    t = Token(user=u, version=1, token=TOK, write_enabled=True)
    t.save()
for t in Token.objects.all():
    print("token", t.pk, t.version, t.enabled, t.write_enabled)
