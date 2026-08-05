def test_parse_sse_events_with_done():
    from app.utils.sse import parse_sse_events

    assert parse_sse_events(['data: {"a":1}', '', 'data: [DONE]', '']) == ['{"a":1}', '[DONE]']


def test_parse_sse_events_multiline_data_and_comments():
    from app.utils.sse import parse_sse_events

    events = parse_sse_events([
        ': comment ignored',
        'data: {"a":',
        'data: 1}',
        '',
    ])
    assert events == ['{"a":\n1}']
