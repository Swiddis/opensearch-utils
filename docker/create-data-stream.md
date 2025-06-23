# Create ss4o data streams

1. Stop the Nginx and Apache log containers for the moment so they don't collide with your templates

2. Create an index template

```json5
// PUT _index_template/ss4o_logs_template
{
  "index_patterns": ["ss4o_logs-*-*"],
  "data_stream": {},
  "template": {
    "settings": {
      "index": {
        "number_of_shards": 1,
        "number_of_replicas": 1,
        "replication": {
          "type": "DOCUMENT"
        }
      }
    },
    "mappings": {
      "properties": {
        "@timestamp": {
          "type": "date"
        },
        "attributes": {
          "properties": {
            "data_stream": {
              "properties": {
                "dataset": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                },
                "namespace": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                },
                "type": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                }
              }
            }
          }
        },
        "body": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        },
        "communication": {
          "properties": {
            "source": {
              "properties": {
                "address": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                },
                "ip": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                }
              }
            }
          }
        },
        "event": {
          "properties": {
            "category": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "domain": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "kind": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "name": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "result": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "type": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "http": {
          "properties": {
            "flavor": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "request": {
              "properties": {
                "method": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                }
              }
            },
            "response": {
              "properties": {
                "bytes": {
                  "type": "long"
                },
                "status_code": {
                  "type": "long"
                }
              }
            },
            "url": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "observedTimestamp": {
          "type": "date"
        },
        "spanId": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        },
        "traceId": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        }
      }
    }
  }
}
```

3. Delete existing ss4o log indices:

```
DELETE ss4o_logs-*
```

4. Create data streams for each log group:

```
// Create separately
PUT _data_stream/ss4o_logs-nginx-prod
PUT _data_stream/ss4o_logs-apache-prod
```

5. Restart the log containers

6. When you cat indices, you'll see numbered data streams

```
GET _cat/indices

...
yellow open .ds-ss4o_logs-nginx-prod-000001  eP9s5kpJQ9WGMyEb9Zu8SQ 1 1  3 0   208b   208b
yellow open .ds-ss4o_logs-apache-prod-000001 HBhsukJNSryyVqEOFNGBig 1 1  4 0   208b   208b
...
```
