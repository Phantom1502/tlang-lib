from setuptools import setup, find_packages

setup(
    name="tlang-lib",
    version="0.1.19",
    description="Tlang library",
    
    # 1. Báo cho setuptools biết root của code nằm ở thư mục 'app'
    package_dir={"": "app"},
    
    # 2. Tìm tất cả các package bên trong thư mục 'app' (sẽ tìm ra 'tlang')
    packages=find_packages("app"),
    
    python_requires=">=3.10",
    install_requires=[
        "pandas>=2.0",
        "numpy>=1.24",
        "matplotlib",
        "mplfinance",
    ],
)