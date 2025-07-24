#!/usr/bin/env python3
import sys
import datetime

TOOL_NAME = "sonar-loc"

def is_prime(n: int) -> bool:
    """Check if a number is prime."""
    if n <= 1:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True

def start_clock() -> datetime.datetime:
    """Returns the now timestamp"""
    return datetime.datetime.now()


def stop_clock(start_time: datetime.datetime) -> None:
    """Logs execution time"""
    print(f"Total execution time: {datetime.datetime.now() - start_time}")

def main(max_nbr: int) -> None:
    """sonar-loc entry point"""
    start_time = start_clock()
    primes = [i for i in range(max_nbr) if is_prime(i)]
    print(f"Primes = {', '.join([str(i) for i in primes])}")
    stop_clock(start_time)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {TOOL_NAME} <max_nbr>")
        sys.exit(1)
    main(int(sys.argv[1]))
    sys.exit(0)
