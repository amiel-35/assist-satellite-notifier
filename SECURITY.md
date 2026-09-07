# Security policy

Assist Satellite Notifier announces messages on Assist satellites you
already control. It makes no outbound network call of its own: everything
it does is a single `assist_satellite.announce` action call on your own
Home Assistant instance.

## About `deny_domains`

The one security-relevant behaviour this integration owns is the
`deny_domains` list: by default, a call whose `data.source_entity` belongs
to `alarm_control_panel` or `lock` is refused and logged instead of being
spoken out loud.

**It is an optional safety net, not a guarantee, and it is not a security
boundary.** It applies only when a call chooses to declare
`data.source_entity`; it does not inspect the message text; and it is not
reachable from the `NotifyEntity` surface, which has no `data` payload at
all. A message about your alarm sent without `data.source_entity` is
announced like any other. Its purpose is to turn "never say the alarm out
loud" into a setting an automation opts into, so a wiring mistake in one
automation is caught by configuration rather than by review.

In particular, `deny_domains` is no defence against anyone who can already
call actions on your Home Assistant instance: at that point they can call
`assist_satellite.announce` directly and never touch this integration.

## About quiet hours

Quiet hours are a courtesy, not a control. `data.priority: "critical"`
bypasses them by design, and any caller can set it.

## Reporting

If you find a way to bypass either check *within* that stated scope, or
any other vulnerability (for example a way to make this integration
announce on an unintended satellite), please open a private security
advisory on GitHub (Security → Report a vulnerability) rather than a
public issue. You will get an answer within 14 days.

Supported versions: the latest minor release only.
