# Changelog

## [0.4.1](https://github.com/haggqvist/cbor-model/compare/v0.4.0...v0.4.1) (2026-04-23)


### Bug Fixes

* emit PEP 695 type aliases as top-level CDDL rules ([#7](https://github.com/haggqvist/cbor-model/issues/7)) ([3c681b2](https://github.com/haggqvist/cbor-model/commit/3c681b2f28358e1c3a66d2b475019683b1b35329))
* include CBOR tag on models in CDDL ([#8](https://github.com/haggqvist/cbor-model/issues/8)) ([c9bb5b5](https://github.com/haggqvist/cbor-model/commit/c9bb5b5143b0470d112fc91361db79c7c1560f2b))

## [0.4.0](https://github.com/haggqvist/cbor-model/compare/v0.3.0...v0.4.0) (2026-04-22)


### Features

* add aliases for common int types ([cc1903c](https://github.com/haggqvist/cbor-model/commit/cc1903cccc44dd5cf9cdc1ea9a23b60aa964668d))
* produce CDDL for enums as choice ([49137ad](https://github.com/haggqvist/cbor-model/commit/49137ad2c31426bedc36d4e763f1e5e606adef99))


### Bug Fixes

* emit precise RFC 8610 integer bounds ([33c9a03](https://github.com/haggqvist/cbor-model/commit/33c9a0346e64a31dcc467e87645f9e8118f967df))
* enforce RFC 8610 .size bounds for strings and bytes ([c5defb9](https://github.com/haggqvist/cbor-model/commit/c5defb9b742bb63f35fe6052f0d78b062359e8b5))

## [0.3.0](https://github.com/haggqvist/cbor-model/compare/v0.2.0...v0.3.0) (2026-04-22)


### Features

* emit snake_case named keys and add CBORField.description ([7a22520](https://github.com/haggqvist/cbor-model/commit/7a225207613e13c8b8202c38126ec22a2b7c5985))


### Bug Fixes

* remove extra trailing comma for description ([e18d0d6](https://github.com/haggqvist/cbor-model/commit/e18d0d69f624c7e2a8779559488404b87ce18001))

## [0.2.0](https://github.com/haggqvist/cbor-model/compare/v0.1.0...v0.2.0) (2026-04-15)


### Features

* add bstr wrapping to CBORField ([7df112f](https://github.com/haggqvist/cbor-model/commit/7df112f92914f656e0be155f22453b6023657ca5))


### Bug Fixes

* produce correct CDDL for Literal ([3af38d7](https://github.com/haggqvist/cbor-model/commit/3af38d7c13d929476a844a56665ebc19ff5b6892))
* support X|Y union syntax on python &lt; 3.14 ([cb6163c](https://github.com/haggqvist/cbor-model/commit/cb6163c4edfab354a0e43bf15a383ab6050d2b01))

## 0.1.0 (2026-03-11)


### Features

* initial implementation ([2d040b4](https://github.com/haggqvist/cbor-model/commit/2d040b4247feb06233db17d300ddbd64820660b5))
