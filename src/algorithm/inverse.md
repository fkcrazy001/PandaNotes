# 模逆元

模意义下乘法运算的逆元，并讨论它的常见求解方法。

## 概念引入

乘法/加法/减法 对于模运算都有 *分配律* ,也就是说对于 

$$
(A\*B\*C) \bmod mo == ((A \bmod mo)\*(B \bmod mo)\*(C \bmod mo))\ \bmod mo
$$

这样的好处是 A * B * C 很有可能会超过数据范围，而取模之后再做乘法，就不会超过数据范围了。

但是对于除法，这个定律就不成立，也就是说 
$$
(A \div B) \bmod mo \neq (A \bmod mo) \div (B \bmod mo)
$$

由此引入 模逆元 定义, 将除法转变为乘法。

## 定义

模逆元： 对于一个数 a，如果存在b使得 $$ab === 1 (\bmod m)$$ 就说b是a在模m意义下的逆元。

前提： 有解的前提是 gcd(a,m) == 1， 且这个解在[0,m-1] 范围内仅存在一个。 关于这个证明，看这里 <https://oi-wiki.org/math/number-theory/linear-equation/> 。

## 算法

用到了扩展欧几里得算法。

```py3
# Extended Euclidean algorithm.
def ex_gcd(a, b):
    if b == 0:
        return 1, 0
    else:
        x1, y1 = ex_gcd(b, a % b)
        x = y1
        y = x1 - (a // b) * y1
        return x, y


# Returns the modular inverse of a modulo m.
# Assumes that gcd(a, m) = 1, so the inverse exists.
def inverse(a, m):
    x, y = ex_gcd(a, m)
    return (x % m + m) % m
```