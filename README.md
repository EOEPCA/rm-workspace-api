<!-- PROJECT SHIELDS -->
<!--
*** See the bottom of this document for the declaration of the reference variables
*** for contributors-url, forks-url, etc. This is an optional, concise syntax you may use.
*** https://www.markdownguide.org/basic-syntax/#reference-style-links
-->

[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![MIT License][license-shield]][license-url]

<!-- PROJECT LOGO -->
<br />
<p align="center">
  <a href="https://github.com/EOEPCA/rm-workspace-api">
    <img src="images/logo.png" alt="Logo" width="80" height="80">
  </a>

  <h3 align="center">EOEPCA Workspace API (v2)</h3>
  
  <p align="center">
    This repository includes the EOEPCA Workspace API component
    <br />
    <a href="https://github.com/EOEPCA/rm-workspace-api"><strong>Explore the docs »</strong></a>
    <br />
    <a href="https://github.com/EOEPCA/rm-workspace-api">View Demo</a>
    ·
    <a href="https://github.com/EOEPCA/rm-workspace-api/issues">Report Bug</a>
    ·
    <a href="https://github.com/EOEPCA/rm-workspace-api/issues">Request Feature</a>
  </p>
</p>

<!-- TABLE OF CONTENTS -->

## Table of Contents

- [About the Project](#about-the-project)
  - [Built With](#built-with)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Testing](#testing)
- [Documentation](#documentation)
- [Usage](#usage)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)
- [Acknowledgements](#acknowledgements)

<!-- ABOUT THE PROJECT -->

## About The Project

[![Product Name Screen Shot][product-screenshot]](https://github.com/EOEPCA/rm-workspace-api)


### Built With

- FastAPI
- Kubernetes Python API

<!-- GETTING STARTED -->

## Getting Started

To get a local copy up and running follow these simple steps.

### Prerequisites

To develop this service both `docker` and `docker-compose` is required.


### Installation

```
docker-compose up
```

### Testing

- `make test` runs the unit tests
- `make lint` runs the code lints

### Run Locally (against eoepca-demo cluster)

`HARBOR_URL="" HARBOR_ADMIN_USERNAME="" HARBOR_ADMIN_PASSWORD="" S3_REGION="eu-central-1" S3_ENDPOINT="
https://minio.develop.eoepca.org" PREFIX_FOR_NAME="ws" WORKSPACE_SECRET_NAME="bucket" KUBECONFIG=~/.kube/config-eoepca-demo uvicorn --reload --host=0.0.0.0 --port 5000 --log-level=info --reload workspace_api:app`

## Documentation

Documentation for the Workspace API:
* [Wiki Pages](https://github.com/EOEPCA/rm-workspace-api/wiki)

<!-- USAGE EXAMPLES -->

<!-- ROADMAP -->

## Roadmap

See the [open issues](https://github.com/EOEPCA/rm-workspace-api/issues) for a list of proposed features (and known issues).

<!-- CONTRIBUTING -->

## Contributing

Contributions are what make the open source community such an amazing place to be learn, inspire, and create. Any contributions you make are **greatly appreciated**.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

<!-- LICENSE -->

## License

Distributed under the Apache-2.0 License. See `LICENSE` for more information.

<!-- CONTACT -->

<!-- ACKNOWLEDGEMENTS -->

## Acknowledgements

- README.md is based on [this template](https://github.com/othneildrew/Best-README-Template) by [Othneil Drew](https://github.com/othneildrew).

<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->

[contributors-shield]: https://img.shields.io/github/contributors/EOEPCA/rm-workspace-api.svg?style=flat-square
[contributors-url]: https://github.com/EOEPCA/rm-workspace-api/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/EOEPCA/rm-workspace-api.svg?style=flat-square
[forks-url]: https://github.com/EOEPCA/rm-workspace-api/network/members
[stars-shield]: https://img.shields.io/github/stars/EOEPCA/rm-workspace-api.svg?style=flat-square
[stars-url]: https://github.com/EOEPCA/rm-workspace-api/stargazers
[issues-shield]: https://img.shields.io/github/issues/EOEPCA/rm-workspace-api.svg?style=flat-square
[issues-url]: https://github.com/EOEPCA/rm-workspace-api/issues
[license-shield]: https://img.shields.io/github/license/EOEPCA/rm-workspace-api.svg?style=flat-square
[license-url]: https://github.com/EOEPCA/rm-workspace-api/blob/master/LICENSE
[product-screenshot]: images/screenshot.png
