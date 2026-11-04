# simple-message-webhook

A small HTTP inbox on AWS. One thing posts a message to a URL, and something else reads it back later. It's for devices that can poll a URL but can't receive a push.

Every path is its own inbox, so `/kitchen`, `/home/desk` and `/` are kept apart. Messages expire after three days.

## What's in the stack

- A Lambda function (FastAPI, via Mangum) behind a function URL
- A DynamoDB table keyed by inbox and message id, with a TTL
- Two keys in SSM Parameter Store, one for writing and one for reading
- A log group that keeps logs for three days (the logs include message bodies)

## Posting

Send a POST with the write key. JSON is stored as it is, and anything else is kept as a JSON string, so a body of `hello` comes back as `"hello"`. Bodies over 4 KB get a 413.

```sh
curl -X POST "$URL/kitchen" \
  -H "Authorization: Bearer $WRITE_KEY" \
  -d '{"source": "mail", "subject": "Lunch"}'
```

```json
{"id": "019a4f3c-7e21-7c3a-9b1d-5f0e2a6c8d41", "inbox": "/kitchen", "received_at": "2026-11-04T10:02:11.123456Z", "expires_at": "2026-11-07T10:02:11Z"}
```

## Reading

Send a GET with the read key. Messages come back oldest first, 20 at a time (`?limit=` takes 1 to 100), and `more` is true when others are waiting.

```sh
curl "$URL/kitchen?clear=true" -H "Authorization: Bearer $READ_KEY"
```

```json
{"inbox": "/kitchen", "more": false, "messages": [{"id": "019a4f3c-7e21-7c3a-9b1d-5f0e2a6c8d41", "received_at": "2026-11-04T10:02:11.123456Z", "payload": {"source": "mail", "subject": "Lunch"}}]}
```

A GET deletes nothing unless you add `clear=true`. With it, only the messages in that response are deleted, so anything that arrives while you're reading waits for the next GET.

A missing or unknown key gets a 401. Using the read key to post, or the write key to read, gets a 403.

## Deploying

You need the AWS SAM CLI, the AWS CLI and uv, and a profile for the account you're deploying to. The region is set in `samconfig.toml` and `deploy.sh`.

```sh
AWS_PROFILE=<profile> ./deploy.sh
```

The first deploy creates both keys in SSM and prints them. After that, `deploy.sh` leaves them alone. The URL is in the stack's `WebhookUrl` output.

To read a key again:

```sh
aws ssm get-parameter --with-decryption \
  --name /simple-message-webhook/read-key \
  --query Parameter.Value --output text
```

To rotate a key, overwrite it in place. The function picks up the new key within five minutes, and the old one works until then.

```sh
aws ssm put-parameter --overwrite --type SecureString \
  --name /simple-message-webhook/write-key \
  --value="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')"
```

## Development

```sh
uv sync
uv run pytest
```

The tests use moto, so they don't need an AWS account.
