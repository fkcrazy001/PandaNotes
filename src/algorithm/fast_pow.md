# 快速幂

## 背景

假设要算 a^n ，但是这个n如果特别大（比如说10^9），如果用常规方法，那么复杂度将会是 o(n) 级别的。这在很多算法题目中都会超时。

快速幂是可以在 o(logn) 时间内完成这个计算的算法，通常搭配上取模，因为这个数会很大。


## 算法思想

!<https://oi-wiki.org/math/binary-exponentiation/>

核心是这里：
![fp](./images/fast_pow.png)

如果n对应的 t 位置上的bit 为1，那么就让 res = res * a^(2^bit)

## 算法实现

```py3
def fast_pow(a:int,n:int,mod:int=0)->int:
    res = 1
    while n:
        if n & 1:
            res = res  * a
            if mod:
                res %= mo
        a = a * a
        if mod:
            a %= mod
        n>>=1
    return res
```


python 的 pow 函数天生就有这个功能，可以看情况使用