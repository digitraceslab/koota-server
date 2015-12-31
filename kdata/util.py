
def luhn1(num, check=False):
    """Luhn algorithm mod 16"""
    factor = 2
    #if check:
    #    factor = 1
    sum = 0
    base = 16
    digits = 2
    base = base**digits

    if check:
        sum = int(num[-digits:], 16)
        num = num[:-digits]
    # Starting from the right, work leftwards
    # Now, the initial "factor" will always be "1"
    # since the last character is the check character
    #for (int i = input.Length - 1; i >= 0; i--) {
    for char in reversed(num):
        addend = factor * int(char, 16)

        # factor alternates between 1 and 2
        factor = 2-factor+1

        # Sum the digits of the "addend" as expressed in base "n"
        addend = (addend // base) + (addend % base);
        sum += addend

    remainder = sum % base
    #print remainder, type(remainder)

    if check:
        return remainder == 0
    else:
        # Computing check digits
        checkCodePoint = (base - remainder) % base
        return '%x'%checkCodePoint

def luhn2(num, check=False):
    factor = 2
    #if check:
    #    factor = 1
    sum = 0
    #base = 16
    #digits = 2
    #base = base**digits

    num = int(num, 16)
    if check:
        #sum = int(num[-digits:], 16)
        #num = num[:-digits]
        sum = num & 255
        num = num >> 8

    #for char in reversed(num):
    while num > 0:
        #addend = factor * int(char, 16)
        addend = factor * (num&15)
        num = num >> 4   # advance to next digits

        # factor alternates between 1 and 2
        factor = 2-factor+1

        # Sum the digits of the "addend" as expressed in base "n"
        #addend = (addend / base) + (addend % base);
        #print addend
        addend = (addend >> 8) + (addend & 255)
        sum += addend
        #print hex(num), sum, addend

    remainder = sum % 256
    #print remainder, type(remainder)

    if check:
        return remainder == 0
    else:
        # Computing check digits
        checkCodePoint = (256 - remainder) % 256
        return '%02x'%checkCodePoint
luhn = luhn2

def add_checkdigits(num):
    return num + luhn(num)
def check_checkdigits(num):
    return luhn(num, check=True)

def test_luhn():
    import random
    random.seed(13)
    for num in ['5146abc5fd2',
                hex(random.randint(0,2**31-1))[2:],
                hex(random.randint(0,2**31-1))[2:],
                hex(random.randint(0,2**31-1))[2:],
                hex(random.randint(0,2**31-1))[2:],
                ]+[hex(random.randint(0,2**31-1))[2:] for _ in range(1000000) ] \
        :
        #
        num_swapped = swap2(num+luhn(num))

        #if num[2]=='0' and num[3]=='f':
        #    print num, luhn(num)
        #    print ('swap2', num, luhn(num), swap2(num), luhn(swap2(num)), )

        assert luhn(num+luhn(num), check=True), \
            (num, luhn(num), )

        assert len(num)<4 or num[2]==num[3] or not luhn(num_swapped, check=True), \
            ('swap2', num, luhn(num), swap2(num), luhn(swap2(num)), )

def swap2(num):
    return num[:2]+num[3:4]+num[2:3]+num[4:]
