import requests
import os.path
import shutil
from io import BytesIO
import gzip
import libarchive

BASE_PATH = os.path.dirname(os.path.abspath(__file__))

SERVER = "http://ftp.de.debian.org/debian"
ARCHITECTURE = "arm64"
VERSION = "bookworm"
TYPE = "main"
DOWNLOAD_RECOMMENDS = False

WANTED_PACKAGES = [
    "python3-pyqt6",
    "python3-pyqt6.qtwebengine",
    "python3-dbus.mainloop.pyqt6",

]
IGNORE_DEPENDENCIES = [
    "python3",
    "python3-dbus",
    "libpython3.11",
    "x11-common"
]


class Main:
    def __init__(self):
        self.packages = {}
        self.alt_package_mapping = {}
        self.downloaded_packages = []

        print(f"Server: {SERVER}")
        print(f"Version: {VERSION}")
        print(f"Architecture: {ARCHITECTURE}")
        print(f"Package Types: {TYPE}")
        print(f"Recommends: {str(DOWNLOAD_RECOMMENDS)}")
        print(f"Wanted Packages: {str(WANTED_PACKAGES)}")
        print(f"Ignoring Depends: {str(IGNORE_DEPENDENCIES)}")

        if os.path.exists(os.path.join(BASE_PATH, "packages")):
            shutil.rmtree(os.path.join(BASE_PATH, "packages"))
        os.mkdir(os.path.join(BASE_PATH, "packages"))

        if os.path.exists(os.path.join(BASE_PATH, "output")):
            shutil.rmtree(os.path.join(BASE_PATH, "output"))
        os.mkdir(os.path.join(BASE_PATH, "output"))

        if os.path.exists(os.path.join(BASE_PATH, "tmp")):
            shutil.rmtree(os.path.join(BASE_PATH, "tmp"))
        os.mkdir(os.path.join(BASE_PATH, "tmp"))

        self.get_packages_gz()

        print(f"\nDownloading packages...")
        for package in WANTED_PACKAGES:
            self.get_package(package)
        print(f"Downloaded {len(self.downloaded_packages)} packages!")

        print(f"\nExtracting packages...")
        all_files = os.listdir(os.path.join(BASE_PATH, "packages"))
        for file in all_files:
            print(f"Extracting: {file}")
            os.chdir(os.path.join(BASE_PATH, "tmp"))
            libarchive.extract_file(os.path.join(BASE_PATH, "packages", file))
            os.chdir(os.path.join(BASE_PATH, "output"))
            libarchive.extract_file(os.path.join(BASE_PATH, "tmp", "data.tar.xz"))
        print(f"Extracted {len(all_files)} packages!")
        print(f"\nFinished!")
        shutil.rmtree(os.path.join(BASE_PATH, "tmp"))

    def get_packages_gz(self):
        print("\nFetching packages...")
        packages_gz = requests.get(f"{SERVER}/dists/{VERSION}/{TYPE}/binary-{ARCHITECTURE}/Packages.gz")

        memory = BytesIO()
        memory.write(packages_gz.content)
        memory.seek(0)

        packages_content = gzip.GzipFile(fileobj=memory).read()
        packages_content = packages_content.strip(b"\n")
        packages_content = packages_content.split(b"\n\n")

        for package in packages_content:
            package_data = {}

            for line in package.splitlines():
                line = line.decode("utf-8")
                if line.startswith("Package: "):
                    package_data["name"] = line.replace("Package: ", "")
                elif line.startswith("Version: "):
                    package_data["version"] = line.replace("Version: ", "")
                elif line.startswith("Depends: "):
                    package_data["depends"] = self.packages2dict(line.replace("Depends: ", ""))
                elif line.startswith("Recommends: "):
                    package_data["recommends"] = self.packages2dict(line.replace("Recommends: ", ""))
                elif line.startswith("Filename: "):
                    package_data["url"] = line.replace("Filename: ", "")
                elif line.startswith("SHA256: "):
                    package_data["hash"] = line.replace("SHA256: ", "")
                elif line.startswith("Provides: "):
                    provides = line.replace("Provides: ", "")
                    provided_package_data = self.packages2dict(provides)
                    for provided_package in provided_package_data.values():
                        if provided_package["name"] not in self.alt_package_mapping.keys():
                            self.alt_package_mapping[provided_package["name"]] = []
                        self.alt_package_mapping[provided_package["name"]].append(package_data["name"])

            self.packages[package_data["name"]] = package_data

        print(f"Fetched {len(self.packages)} packages!")

    @staticmethod
    def packages2dict(depends):
        depends_dict = {}

        for depend_package in depends.split(", "):
            depend_package_data = {}

            if "|" in depend_package:
                depend_package = depend_package.split("|")[0].strip()

            if " " not in depend_package and ":" in depend_package:
                depend_package = depend_package.split(":")
                depend_package_data["name"] = depend_package[0]
                depend_package = depend_package[0]

            elif " " not in depend_package:
                depend_package_data["name"] = depend_package

            elif depend_package.endswith(")"):
                depend_package = depend_package.split(" ", 1)
                depend_package_version = depend_package[1][1:-1]
                compare_operation = depend_package_version[:2].strip()
                depend_package_version = depend_package_version[2:].strip()

                depend_package = depend_package[0]
                depend_package_data["name"] = depend_package
                depend_package_data[compare_operation] = depend_package_version

            if depend_package in depends_dict.keys():
                depends_dict[depend_package] = {**depends_dict[depend_package], **depend_package_data}
                continue

            depends_dict[depend_package] = depend_package_data

        return depends_dict

    def get_package(self, package, dependency=False, recommended=False):
        try:
            if package in self.packages.keys():
                package_data = self.packages[package]

                if dependency:
                    print(f"Downloading (Dependency): {package}")
                elif recommended:
                    print(f"Downloading (Recommended): {package}")
                else:
                    print(f"Downloading: {package}")

                package_file = requests.get(f"{SERVER}/{package_data['url']}")
                package_filename = str(package_data['url']).rsplit("/", 1)[1]

                with open(os.path.join(BASE_PATH, "packages", package_filename), "wb") as file:
                    file.write(package_file.content)
                self.downloaded_packages.append(package)

                if "depends" in package_data.keys():
                    for dependency in package_data["depends"].keys():
                        if dependency not in IGNORE_DEPENDENCIES and dependency not in self.downloaded_packages:
                            self.get_package(dependency, dependency=True)

                if "recommends" in package_data.keys() and DOWNLOAD_RECOMMENDS:
                    for recommended in package_data["recommends"].keys():
                        if recommended not in IGNORE_DEPENDENCIES and recommended not in self.downloaded_packages:
                            self.get_package(recommended, recommended=True),
            else:
                print(f"Warning: {package} not found, checking if it is provided by another package...")
                if package in self.alt_package_mapping.keys():
                    for package_that_provides in self.alt_package_mapping[package]:
                        if package_that_provides in self.downloaded_packages:
                            print(f"Success: {package} is provided by {package_that_provides}, which was already downloaded")
                        else:
                            print(f"Success: {package} is provided by {package_that_provides}")
                            self.get_package(package_that_provides, dependency=True)
                        self.downloaded_packages.append(package)
                else:
                    print(f"Error: {package} not found!")
                    exit()

        except Exception as e:
            print(f"Error: {e}")
            exit("File not found or no internet access")


Main()
