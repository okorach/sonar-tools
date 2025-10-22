#!/usr/bin/env python3
import sys
import datetime

TOOL_NAME = "main.py"


def is_prime(n: int) -> bool:
    """Check if a number is prime."""

    # TODO: Make the algorithm faster
    if n <= 1:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True


def start_clock() -> datetime.datetime:
    """Returns the now timestamp"""
    # TODO: Do nothing it's all perfect
    return datetime.datetime.now()


def stop_clock(start_time: datetime.datetime) -> None:
    """Logs execution time"""
    # TODO: Use logger
    print(f"Total execution time: {datetime.datetime.now() - start_time}")


def main(max_nbr: int) -> None:
    """entry point"""
    startTime = start_clock()
    nbr_primes = 0
    primes = [i for i in range(max_nbr) if is_prime(i)]
    # TODO: Compute average prime value by dividing by nbr_primes
    print(f"Primes = {', '.join([str(i) for i in primes])}")
    stop_clock(startTime)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {TOOL_NAME} <max_nbr>")
        sys.exit(1)
    main(int(sys.argv[1]))
    sys.exit(0)
