"""src/scheduling — Cizelgeleme motoru iskeleti (PLAN_DEMO1.md Faz 8).

Alt moduller:
  models      — Order + Capacity dataclass'lari, JSON round-trip, dogrulama
  rules       — Agirlikli oncelik skorlama ve siralama (EDD default)
  batcher     — Oncelik sirasindaki siparislerden kapasite partileri
  feasibility — Parti plani + kapasite => termin asim uyarilari
  report      — Ozet dict + markdown raporu
"""
